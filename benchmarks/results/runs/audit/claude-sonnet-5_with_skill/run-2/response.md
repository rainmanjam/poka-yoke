Bash calls aren't going through in this session, so I did this as a manual three-lens read rather than running the detector script first pass — the skill treats the script as a supplement anyway, and I read every function in full.

**Scope**: `benchmarks/fixtures/payments.ts`, 105 lines, all 6 exported functions.
**Verdict**: the webhook handler will execute a real charge for an unauthenticated, unverified POST body — everything else here is serious, but that one doesn't even require a bug to trigger, it requires no fix to already be broken.

## Findings

### 1. Webhook events are never authenticated — Money movement + security bypass / trivial
**Where**: `payments.ts:93-100`
**Mistake**: POST anything shaped like `{"type":"invoice.paid","data":{"customer":"...","amount":...}}` to whatever endpoint calls `handleWebhook`. There's no `stripe-signature` check.
**Consequence**: `chargeCustomer` runs with attacker-supplied `customer` and `amount`. Real charge, real customer, zero authentication. Silent — no rejected-request log, nothing to distinguish it from a genuine Stripe event.
**Today**: None.
**Device** → **Control**:
```ts
const sig = req.headers["stripe-signature"];
const event = stripe.webhooks.constructEvent(rawBody, sig, endpointSecret); // throws on mismatch
```
Only a signature-verified `Stripe.Event` should be able to reach the charge path — make that the type the rest of the function requires.

### 2. `chargeCustomer` has no idempotency key — Money movement / reachable by an ordinary retry
**Where**: `payments.ts:44-60`
**Mistake**: the network call to Stripe fails *after* the charge actually succeeded (timeout, dropped response). The internal `if (retry)` branch — or any external caller retrying on `null` — calls `stripe.charges.create` again with nothing tying the two attempts together.
**Consequence**: customer charged twice. Nothing distinguishes the second charge object from the first; it looks like a normal success.
**Today**: None — `retry` is a boolean that re-runs the same unsafe call, not a device.
**Device** → **Control** (Stripe de-dupes server-side on the key):
```ts
async function chargeCustomer(customerId: string, amountCents: number, idempotencyKey: IdempotencyKey, ...) {
  return stripe.charges.create({ customer: customerId, amount: amountCents, currency }, { idempotencyKey });
}
```
Make the key required, and pass the *same* key on webhook redelivery (Stripe's `event.id` is a natural choice) so retries collapse to one charge.

### 3. `transfer` isn't transactional — Money movement / silent corruption
**Where**: `payments.ts:17-35`
**Mistake**: two concurrent transfers from the same account both read the balance, both pass the `< amount` check, both debit — net result can go negative. Separately, if the credit `update` throws after the debit `update` succeeds, money leaves `fromAccount` and never lands anywhere.
**Consequence**: silent overdraft or silently vanished money, no rollback.
**Today**: None.
**Device** → **Control**:
```ts
await db.$transaction(async (tx) => {
  const debited = await tx.accounts.updateMany({
    where: { id: fromAccount, balance: { gte: amount } }, // re-checks atomically
    data: { balance: { decrement: amount } },
  });
  if (debited.count === 0) throw new Error("insufficient funds");
  await tx.accounts.update({ where: { id: toAccount }, data: { balance: { increment: amount } } });
});
```

### 4. `purgeCanceledAccounts()` with no argument deletes every canceled account ever — Irreversible data loss / trivial
**Where**: `payments.ts:80-91`
**Mistake**: call it with no argument — the natural reading is "purge old ones" — and `cutoff` defaults to `new Date()`, i.e. now. The raw `DELETE` then matches *every* account canceled at any point in the past.
**Consequence**: full, irreversible deletion of canceled-account history, run through `$executeRawUnsafe` for no reason a parameterized query couldn't handle.
**Today**: None — the optional parameter *is* the trap.
**Device** → **Control**:
```ts
export async function purgeCanceledAccounts(olderThan: Date) { // required, no default
  return db.accounts.deleteMany({ where: { status: "canceled", canceledAt: { lt: olderThan } } });
}
```
Drop `$executeRawUnsafe` entirely — Prisma's `deleteMany` does the same thing without hand-built SQL.

### 5. `chargeCustomer` swallows its own failure — Silent wrong business state
**Where**: `payments.ts:55-59`, called from `payments.ts:98`
**Mistake**: any Stripe error (declined card, network fault) is caught and turned into `return null`. `handleWebhook` calls `await chargeCustomer(...)` and never inspects the result.
**Consequence**: an invoice comes in marked paid, the charge actually fails, and nothing downstream — no log, no retry, no alert — knows money wasn't collected.
**Today**: None (X1 swallowed error).
**Device** → **Control** via a typed result the caller can't ignore:
```ts
type ChargeResult = { ok: true; charge: Charge } | { ok: false; error: unknown };
```
then `handleWebhook` must branch on `.ok` — there's no `null` to accidentally not-check.

### 6. `transfer(fromAccount, toAccount, ...)` — swappable same-type IDs — Money movement / plausible-looking
**Where**: `payments.ts:17`
**Mistake**: `transfer(b, a, amount)` instead of `transfer(a, b, amount)` — compiles, passes review, moves money the wrong direction.
**Consequence**: silent, wrong-direction transfer.
**Today**: None.
**Device**: branded `SourceAccountId` / `DestinationAccountId` types → **Control**. Cheaper fallback if branding is too big a lift right now: named/options-object call (`transfer({ from, to, amount })`) → **Warning**, visible in review but not compiler-enforced.

### 7. `updateSubscription`'s switch is non-exhaustive — Silent feature/billing mismatch
**Where**: `payments.ts:67-78`
**Mistake**: any status besides `"active"`/`"canceled"` (`"past_due"`, `"trialing"`, `"paused"`, a typo) writes to the DB fine, but the switch has no matching arm — feature access silently stays whatever it was.
**Consequence**: billing state and product access drift apart with no error anywhere.
**Today**: None.
**Device** → **Control**: a literal-union `status` type instead of `string`, plus an `assertNever` default arm — adding a status becomes a compile error until every switch handles it.

## Set aside
- `sendReceipt`/`retry` booleans on `chargeCustomer` (C2, call-site readability) — real, but smaller blast radius than the idempotency issue on the same function.
- Money as `number` throughout (C6) — pervasive, best fixed once alongside the idempotency-key refactor rather than as its own finding.
- Unused `WEBHOOK_TIMEOUT` read (line 95) — dead code, not a hazard on its own; worth deleting or wiring up while you're in there for #1/#2.

Want me to write this to `docs/poka-yoke/audit-2026-08-22.md`, or start applying any of these (I'd do #1 and #2 first — they're the ones that actually cause money to move incorrectly)?