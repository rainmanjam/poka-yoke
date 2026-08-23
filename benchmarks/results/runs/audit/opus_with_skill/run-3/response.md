Couldn't run `detect_hazards.py` — both Bash and the sandbox need approval this session, so this is the manual pass (three lenses over each signature). The detector would only have confirmed the mechanical shapes anyway; per the skill it's a first pass, not an oracle.

**One thing before the findings:** this file isn't a production billing module. Its header says it's an eval fixture, deliberately hazard-rich, and it lives in `benchmarks/fixtures/`. So "before we ship it" doesn't apply — nothing here charges a real card. The hazards are real hazards though, and they're planted precisely because they pass review in real codebases, so the audit below is worth having. Flagging it because if you thought this was the live module, that's the more urgent correction.

---

# Poka-Yoke Audit — benchmarks/fixtures/payments.ts — 2026-08-22

**Scope**: one file, 105 lines, 7 exported functions.
**Verdict**: `transfer` accepts a negative amount, which lets any caller drain any account they can name — that's an authorization bypass, not a rounding bug, and it outranks everything else here.

## Findings

### 1. Negative transfer amount reverses the direction of money — Money movement / Silent
**Where**: `benchmarks/fixtures/payments.ts:17`
**Mistake**: Call `transfer(myAccount, victimAccount, -100)`.
**Consequence**: `from.balance < amount` is `1000 < -100` → false, so the guard passes. Then `from.balance - (-100)` credits the caller and `to.balance + (-100)` debits the target. Money flows backwards. Completely silent; the return value reports a normal-looking transfer.
**Today**: None.
**Device**: A `PositiveAmount` parse at the boundary — the type cannot hold a non-positive value, so the check can't be skipped downstream.

```ts
const Amount = z.number().int().positive().brand<"Amount">();
export async function transfer(from: SourceAccount, to: DestAccount, amount: Amount)
```

→ **Control.**

### 2. `purgeCanceledAccounts()` with no argument deletes every canceled account — Irreversible data loss / Forgetting only
**Where**: `benchmarks/fixtures/payments.ts:80`
**Mistake**: Call it with no argument, which is the natural reading of an optional parameter named `olderThan`.
**Consequence**: `olderThan || new Date()` makes the cutoff *now*, so the retention window is "all of history." Hard `DELETE`, no cap, no soft-delete, unrecoverable. Separately, the returned count comes from a *different* query than the one that deleted — rows canceled between the two statements are deleted but not counted, so the number you log is a plausible lie.
**Today**: None.
**Device**: Make `cutoff` required (F3), cap the affected rows and refuse above it (F2), and take the count from the delete's own result.

```ts
export async function purgeCanceledAccounts(cutoff: Date, opts: { maxRows: number }) {
  const { count } = await db.accounts.deleteMany({
    where: { status: "canceled", canceledAt: { lt: cutoff } },
  });
  if (count > opts.maxRows) throw new Error(`refusing: ${count} > ${opts.maxRows}`);
  return count;
}
```

→ **Control.** (The cap needs a transaction to be a true guard rather than a post-hoc alarm — wrap it, or soft-delete so it's reversible.)

Note the `$executeRawUnsafe` template on line 86: injection isn't reachable today because `cutoff` is a `Date`, but the shape invites the next parameter to be a string.

### 3. Webhook charges customers with no signature verification — Security bypass + money / Trivial
**Where**: `benchmarks/fixtures/payments.ts:93`
**Mistake**: Anyone who can reach the endpoint POSTs `{"type":"invoice.paid","data":{"customer":"cus_x","amount":999999}}`.
**Consequence**: Unauthenticated attacker-controlled charge against any customer, for any amount. `JSON.parse` into `any` means nothing validates the shape either — and Stripe's real `invoice.paid` payload has no `amount` field (it's `amount_paid`), so the live path is passing `undefined` as the charge amount. Also `WEBHOOK_TIMEOUT` is read on line 95 and never used.
**Today**: None.
**Device**: `stripe.webhooks.constructEvent(rawBody, sig, secret)` before anything else, then a zod schema per event type. Charging *on* `invoice.paid` is backwards regardless — the invoice is already paid.
→ **Control** on both authenticity and shape.

### 4. Retry re-charges after a timeout — Money / Silent
**Where**: `benchmarks/fixtures/payments.ts:37`
**Mistake**: Pass `retry = true` and hit a network timeout where Stripe actually created the charge.
**Consequence**: Double charge. `catch` can't distinguish "never happened" from "happened, response lost." Then `return null` on failure makes a failed charge indistinguishable from a successful one to any caller that doesn't check — and `handleWebhook` doesn't check. `void sendReceiptEmail(...)` on line 52 discards its error and can fire before the charge settles.
**Today**: None. (This is the shape behind the 340-customer double-charge in your notes.)
**Device**: A **required** `idempotencyKey` parameter, passed to Stripe, backed by `UNIQUE (customer_id, idempotency_key)`. Optional keys are rung zero in a costume. Delete the `retry` boolean — retry belongs to the caller who owns the key. Throw instead of returning `null`.
→ **Control**, but only if the key is reserved in the same transaction as the charge and the stored result is replayed to the second caller; a constraint violation alone tells the retrier nothing about whether attempt one worked.

### 5. Balance check races the debit; the two writes aren't atomic — Silent corruption / Concurrency only
**Where**: `benchmarks/fixtures/payments.ts:21`
**Mistake**: Two transfers on the same account interleave between the read and the write.
**Consequence**: Both pass the balance check against the same stale read; balance goes negative. Independently, the two `update`s on lines 25 and 29 have no transaction — a failure between them destroys money outright. And `from.currency` vs `to.currency` is never compared, so USD 100 becomes JPY 100.
**Today**: None. The `from!` / `to!` assertions also erase the missing-account case.
**Device**: One conditional update inside a transaction — `UPDATE ... SET balance = balance - $1 WHERE id = $2 AND balance >= $1`, both legs in `db.$transaction`, plus `CHECK (balance >= 0)` on the column so no other service or `psql` session can violate it either.
→ **Control**, and the `CHECK` is the durable half.

### 6. Misspelled status silently grants free service — Wrong output / Forgetting only
**Where**: `benchmarks/fixtures/payments.ts:67`
**Mistake**: Call `updateSubscription(id, "cancelled")` — British spelling — or add a `"past_due"` state later.
**Consequence**: The DB write succeeds, the `switch` matches nothing, there's no `default`, and `disableFeatures` never runs. A canceled customer keeps full access, indefinitely, with no error anywhere.
**Today**: None.
**Device**: A literal union `type SubStatus = "active" | "canceled" | ...` plus `default: assertNever(status)`, with `@typescript-eslint/switch-exhaustiveness-check` at error. Adding a state then breaks the build here.
→ **Control**, one line per switch — cheapest device in the file.

### 7. Unbounded discount produces a negative price — Money / Unusual-but-reachable
**Where**: `benchmarks/fixtures/payments.ts:63`
**Mistake**: `applyDiscount(100, 150)`.
**Consequence**: Returns `-50`. A negative price into `chargeCustomer` is a refund you didn't authorize. `percentOff` as a bare `number` is also ambiguous — 0.2 could be 20% or 0.2%. Float arithmetic on money accumulates error across aggregation.
**Today**: None.
**Device**: `z.number().min(0).max(100).brand<"Percent">()`, integer cents throughout, clamp the floor at zero.
→ **Control.**

## Set aside
Four lower-priority hazards, one line each: `Account.status` and `.currency` are bare strings (same C4 shape as #6, lower blast radius); `Account.balance` is a float (subsumed by #7's Money type); the `!` assertions in `transfer` (covered by #5's rewrite); `WEBHOOK_TIMEOUT` read-then-discarded (dead code, no hazard until someone wires it up).

---

`★ Insight ─────────────────────────────────────`
- The ranking is deliberate: finding #6, a silent free-service bug, sits above #7, a crash-adjacent one. Loud failures are cheap — you find them in minutes. A canceled customer keeping access produces no signal at all until someone audits revenue.
- Findings #1, #2, and #7 are the same underlying hazard wearing three costumes: an unconstrained `number` crossing a boundary. One `Money`/`Amount` parse type closes all three, which is why it's worth more than three separate `if` guards.
- Note what #4 asks for that a plain unique constraint doesn't give you: rejecting a duplicate isn't the same as *being* idempotent. The retrier that gets a constraint violation still doesn't know whether the first charge went through — which is exactly how a "fixed" double-charge bug comes back.
`─────────────────────────────────────────────────`

I haven't touched any files — the skill says propose first, and these change interface shapes that ripple to call sites.

Two things worth your call:

**The purge cap policy is a real domain decision, not boilerplate.** In finding #2 I sketched `maxRows` as a throw-above-threshold, but the honest options differ: hard-fail above a cap (safe, wakes someone at 3am when the cutoff is legitimately wide), dry-run-by-default returning the count (safe, but the second call is unguarded), or soft-delete with a retention sweep (reversible, costs you a `deletedAt` column and every query filtering on it). If you want to shape that one, `purgeCanceledAccounts` is the place — 5–10 lines, and the trade-off is really about how often you legitimately purge large batches.

Want me to write this to `docs/poka-yoke/audit-2026-08-22.md`, and do you want the fixes applied to the fixture — or is it meant to stay hazard-rich for the benchmark? If it's the latter, patching it would invalidate your eval baseline, so I'd leave it alone.