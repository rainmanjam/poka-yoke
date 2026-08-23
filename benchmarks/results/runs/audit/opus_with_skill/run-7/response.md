Detector and file-write were both blocked by permissions in this session (`detect_hazards.py` and `docs/poka-yoke/audit-2026-08-22.md` — grant those and I'll rerun/save). So this is a hand-run audit, in the conversation.

One thing worth saying first: the header comment on that file says it's a deliberately hazard-rich eval fixture, not shipping code. I audited it as asked on the assumption its shapes mirror your real module.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-22

**Verdict**: `handleWebhook` parses an unauthenticated body and turns it straight into a charge. Anyone who can POST to that endpoint can bill any customer any amount. Fix that before anything else here.

### 1. Unauthenticated webhook → arbitrary charge — `:93` — money + authz bypass / trivial
**Mistake**: POST arbitrary JSON; `event.data.customer` and `event.data.amount` flow into `chargeCustomer`.
**Consequence**: attacker-chosen charges. Silent — indistinguishable from real traffic. `JSON.parse` also yields `any` (C7), so malformed real events fail deep inside Stripe's client instead of at the edge.
**Today**: None. **Device**: `stripe.webhooks.constructEvent(rawBody, signature, secret)` then zod-parse to a typed event; take `rawBody` and `signature` as required params → **Control**.

### 2. Negative `amount` inverts `transfer` — `:17` — irreversible money movement / one character
**Mistake**: `transfer(a, b, -100)` from an unclamped form, a CSV import, or a refund path that negates.
**Consequence**: `from.balance < amount` is *false* for every negative amount, so it passes. `from` is credited, `to` is debited. Direction inverts. Totally silent.
**Today**: None. **Device**: a `Money` smart constructor that rejects non-positive integers → **Control**.

### 3. Debit and credit outside a transaction; destination validated *after* the debit — `:25-32` — irreversible loss / forgetting
**Mistake**: pass a destination ID that doesn't exist, or have the second `update` fail (deadlock, timeout, dropped connection).
**Consequence**: line 25 already debited. Line 31 dereferences `to!` on `null` and throws. Money gone, credited to nobody, no rollback. The `!` assertions are what hide it — `to` is never checked while it still matters.
**Today**: None. **Device**: `findUniqueOrThrow` both accounts *before* any write, both writes in one `$transaction`, plus `CHECK (balance >= 0)` on the column so no script or psql session can bypass it → **Control**.

### 4. `transfer(from, to, …)` — adjacent strings, swap compiles — `:17` — money / silent
**Consequence**: money moves the wrong way between two real accounts; the funds check just fires against the wrong one.
**Today**: parameter names, which the compiler doesn't read. **Device**: branded `SourceAccount` / `DestinationAccount` → **Control**. Cheaper fallback if branding hits too many call sites: `transfer({ from, to, amount })`, forcing the names at the call site — **Warning**, visible in review, invisible to the compiler.

### 5. Retry with no idempotency key — `:55-58` — duplicate charge / happens on its own
**Mistake**: none required. `retry = true`, a Stripe webhook redelivery, or a queue re-run re-creates a charge that *succeeded but timed out on the response*.
**Consequence**: double billing. You've already had this one — 340 customers.
**Today**: None; the retry *is* the hazard. **Device**: a **required** `idempotencyKey` param passed to Stripe, backed by `UNIQUE (customer_id, idempotency_key)` → **Control**. Derive it from the business event (invoice ID, `event.id`), never a fresh UUID per attempt — that's an optional key in a costume. And reserve the key in the same transaction as the effect, replaying the stored result: a retry that merely hits the constraint has learned nothing about whether the first attempt worked.

### 6. `purgeCanceledAccounts()` deletes every canceled account — `:80-88` — irreversible data loss / the shortest call
**Mistake**: call it with no arguments.
**Consequence**: `olderThan || new Date()` makes the cutoff *now*, matching the entire canceled population. The most destructive call is the easiest to write, and the optional marker reads as "fine to omit." Hard `DELETE`, no cap, no dry run. Quieter bug alongside it: it returns `doomed.length` from the SELECT while the DELETE re-evaluates the predicate independently — the returned count is a number that was never true.
**Today**: None. `Unsafe` in `$executeRawUnsafe` is a naming convention — rung 0. **Device**: required cutoff, `maxRows` cap, `{ apply: false }` dry-run default, delete by collected IDs, parameterized SQL → **Control**.

### 7. Check-then-act on `balance` — `:21-28` — silent money creation / concurrency only
Two overlapping transfers both read 100, both pass the check, both write the *absolute* value 50. Two debits, one deduction. Passes every single-threaded test.
**Device**: `UPDATE accounts SET balance = balance - $1 WHERE id = $2 AND balance >= $1` — 0 rows affected means insufficient funds; check and act become one statement → **Control**.

### 8. `catch { return null }` makes a failed payment look handled — `:55-60` — silent wrong state / forgetting
Declines, network partitions, Stripe outages and malformed input all collapse into one `null` — which `handleWebhook:98` never checks. The webhook returns 200, Stripe stops retrying, the payment is silently abandoned. `null` also erases the bit that matters most: whether the charge happened.
**Device**: a discriminated union → **Control**.
```ts
type ChargeResult =
  | { status: "succeeded"; charge: Charge }
  | { status: "declined"; code: DeclineCode }
  | { status: "unknown"; cause: unknown };   // timed out — may or may not have charged
```
`"unknown"` earns its own variant. "We don't know if the money moved" is a real state, and folding it into `null` is how reconciliation gaps start.

### 9. `updateSubscription(id, "cancelled")` stops billing, leaves features on — `:67-78` — revenue leak / a spelling
Any status that isn't exactly `"active"` or `"canceled"` — the British spelling, `"paused"`, a Stripe status copied verbatim — writes the DB and falls through a `default`-less switch. Same failure when someone adds a status later: every existing switch silently keeps its old behaviour.
**Device**: literal union + `default: assertNever(status)`, and `@typescript-eslint/switch-exhaustiveness-check` repo-wide → **Control**. Follow-on: `status` is assigned by raw write from anywhere (M3), so a single `transitionSubscription()` that rejects illegal transitions is the real fix, with the DB write and feature toggle in one transaction.

### 10. Money as `number`, currency as a defaulted string — `:12-13, 40, 63` — silent wrong amounts / forgetting
`currency = "usd"` is a default for something with no safe default; `handleWebhook` ignores `event.data.currency` entirely, so a EUR invoice gets charged in USD at the same nominal amount. `transfer` never compares `from.currency` to `to.currency`. `applyDiscount` does float arithmetic with no rounding policy and accepts unbounded `percentOff` — `applyDiscount(100, 150)` returns `-50`, a credit.
**Device**: one `Money` type carrying its currency, mixed-currency arithmetic that doesn't typecheck, `Percent` branded to 0–100 → **Control**. (`amountCents` encodes its unit in the name — worth doing, still rung 0.)

## Set aside (5)
- `void sendReceiptEmail(...)` `:52` — floating promise; errors vanish, serverless can exit first. `no-floating-promises` at error → Warning.
- `from!` / `to!` `:21,27,31` — subsumed by #3, but ban `!` by lint here.
- `$executeRawUnsafe` interpolation `:86` — a `Date` today, so not exploitable, but the shape invites the next edit. Parameterizing is free.
- `process.env.WEBHOOK_TIMEOUT` `:95` — read in the handler, never used. Parse all env into typed config at boot.
- `Account.status: string` `:14` — `transfer` never checks it, so frozen/closed accounts can still send.

★ Insight ─────────────────────────────────────
Findings 2, 6 and 8 are the same shape three times: **the unsafe case is the one that requires typing less.** Omit the amount's sign check, omit the cutoff, omit the null check — each omission is silently the destructive branch. The general device isn't more validation, it's inverting which call is short: make the dangerous variant the one you have to spell out (`{ apply: true }`, an explicit `"unknown"` arm).

Nothing here is a bug that's fired yet. #5 is the exception — it already has, and it's the one where the device is fully specified and cheap.
─────────────────────────────────────────────────

**Before I touch anything** — two decisions that shape the rest, and your domain knowledge beats my guess:

1. **Idempotency key scope** (#5). `(customer_id, key)` or `(key)` globally? Global is stricter and catches cross-customer replay; per-customer lets two customers legitimately reuse an order-numbering scheme. Your ledger's shape decides this, and it's the open question from the earlier incident thread.
2. **`ChargeResult["unknown"]`** (#8). When a charge times out, does your system reconcile against Stripe later, or hold the invoice pending? That determines whether `unknown` needs to carry a resumable handle or just an error.

Say go on any subset and I'll apply the devices with `poka-yoke:` marker comments naming the mistake each one blocks, then run the tests.