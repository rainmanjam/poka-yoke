That confirmed — it's the exact benchmark fixture from `benchmarks/fixtures/payments.ts` (header: "Deliberately hazard-rich... every hazard here is one that ships in real codebases and passes review"), used to A/B-test this repo's own poka-yoke skill. Not something on a ship path. I ran the manual three-lens review anyway since the hazards themselves are real and instructive (the detector script needs a separate approval I didn't get back — the manual pass is where this skill's value actually lives, per its own instructions).

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-22

**Scope**: single file, 105 lines, read in full (not a diff — file is committed).
**Verdict**: `handleWebhook` has no signature verification, so anything that reaches it can trigger a real charge against any customer ID — fix that before anything else here matters.

## Findings

### 1. Unauthenticated webhook triggers real charges — Security bypass / Trivial
**Where**: `payments.ts:93`
**Mistake**: POST any body shaped like `{type: "invoice.paid", data: {customer, amount}}` to this endpoint.
**Consequence**: `stripe.charges.create` runs for whatever `customer`/`amount` the caller supplies — no proof the request came from Stripe. `WEBHOOK_TIMEOUT` is read and never used, which reads like a removed signature check rather than one that was never written.
**Today**: None.
**Device**: verify `stripe-signature` against the raw body with `stripe.webhooks.constructEvent` before parsing anything, reject on failure. → **Control**

### 2. Charges have no idempotency key — Irreversible money movement / Silent
**Where**: `payments.ts:37,56-57`
**Mistake**: Stripe retries the webhook (it does this routinely), or the `retry=true` path re-calls `chargeCustomer` after a transient failure.
**Consequence**: two real charges for one invoice. This is the same shape as the 340-customer double-charge incident already diagnosed in this session's history.
**Today**: None — no idempotency key passed to `stripe.charges.create`, and the built-in retry is a second call, not a replay of the first.
**Device**: pass a deterministic idempotency key (`invoice.id` or similar) to Stripe, and a unique constraint on `(customer, idempotency_key)` locally so a duplicate request returns the stored result instead of charging again. → **Control**

### 3. `purgeCanceledAccounts()` with no argument deletes everything — Irreversible data loss / Silent
**Where**: `payments.ts:80-91`
**Mistake**: call `purgeCanceledAccounts()` — the "safe-looking," argument-free call — expecting it to no-op or use some sane retention window.
**Consequence**: `cutoff` defaults to `new Date()` (right now), so every canceled account, regardless of age, matches `canceled_at < cutoff` and gets hard-deleted via raw SQL. The name `olderThan` implies a filter; omitting it removes the filter entirely.
**Today**: None. Also worth noting: the returned count comes from a `findMany` run *before* the `DELETE`, so under concurrent cancellations the reported count and the actual deleted count can diverge — a second silent issue riding on the same code.
**Device**: make the cutoff required, refuse to run with an empty/absent bound; replace `$executeRawUnsafe` string interpolation with a parameterized query; soft-delete (mark purged) instead of hard-delete, or require an explicit `confirm: true` plus a printed row count for the hard-delete path. → **Control**

### 4. Non-atomic transfer, unguarded balance check — Silent corruption / Needs concurrency or partial failure
**Where**: `payments.ts:17-35`
**Mistake**: two concurrent transfers debit the same account, or the process dies between the two `update` calls.
**Consequence**: the balance check (line 21) and the two updates (line 25, 29) aren't in a transaction and aren't atomic — a concurrent second transfer can pass the same balance check before the first update lands (check-then-act race), producing an overdraft; a crash between the two updates deletes money from `from` without it ever reaching `to`. Also: `from!`/`to!` non-null-assert past a lookup that can legitimately return null (unknown account ID), turning a bad ID into a confusing crash instead of a clear error.
**Today**: None.
**Device**: wrap both updates in a DB transaction with a conditional `WHERE balance >= amount` on the debit (turns the check-then-act into one atomic statement); replace the `!` assertions with an explicit not-found check. → **Control**

### 5. Subscription status is a bare string with a non-exhaustive switch — Wrong output, silent / Needs a typo or new status value
**Where**: `payments.ts:67-78`
**Mistake**: pass any status string other than exactly `"active"`/`"canceled"` (a typo, or a legitimate new status like `"past_due"` added later).
**Consequence**: the DB write happens regardless, but the switch has no default/exhaustiveness check, so feature enable/disable silently doesn't run — the DB says one thing, entitlements say another, and nothing logs it. The DB write and the feature toggle also aren't transactional, so a throw inside `enableFeatures` leaves the same inconsistency.
**Today**: None.
**Device**: a literal union type for status with an `assertNever` default arm (compiler-enforced exhaustiveness), and a single transition function that does the DB write and the feature toggle together. → **Control**

## Set aside
- `applyDiscount`: `percentOff` isn't bounded, so >100 produces a negative price — low blast radius, easy to catch in review or with a range check.
- `chargeCustomer`'s boolean flags (`sendReceipt`, `retry`) make call sites unreadable, but they're subsumed by finding #2 — fixing idempotency touches this signature anyway.
- `sendReceiptEmail` fire-and-forget (`void sendReceiptEmail(...)`): a lost receipt is annoying, not dangerous, compared to the above.

Want me to write this to `docs/poka-yoke/audit-2026-08-22.md`, or turn any of these into actual diffs against the fixture?