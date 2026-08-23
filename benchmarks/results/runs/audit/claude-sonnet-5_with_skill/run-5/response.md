One heads-up before the findings: this file's header comment says it's a **deliberately hazard-rich eval fixture** used to benchmark this very skill (`benchmarks/fixtures/`), not the actual billing module. If there's a real billing module elsewhere that this stands in for, point me at it — everything below is real and worth fixing regardless, but "before we ship it" doesn't quite apply to a benchmark fixture.

Scope: `benchmarks/fixtures/payments.ts` in full (105 lines, read directly — the hazard detector script needed interactive approval I didn't get, so this is manual application of the three lenses). Ranked by blast radius × ease of mistake.

## 1. `handleWebhook` charges money with no signature verification — Money/Security · Trivial
**Where**: `benchmarks/fixtures/payments.ts:93-100`
**Mistake**: `JSON.parse(body)` is trusted directly — `event.data.customer` and `event.data.amount` flow straight into a real Stripe charge with no HMAC/signature check against Stripe's webhook secret, and no schema validation.
**Consequence**: anyone who can reach this endpoint can POST a fake `invoice.paid` event and charge an arbitrary Stripe customer an arbitrary amount. Silent — it looks like a normal successful charge.
**Today**: None.
**Device**: verify `stripe-signature` via `stripe.webhooks.constructEvent(body, sig, secret)` before touching the payload, and parse the result through a schema (zod) instead of trusting `any`. → **Control** on both the auth bypass and the unvalidated-input hazard (C7).

## 2. `chargeCustomer` has no idempotency key — Money · Automatic (no misuse needed)
**Where**: `benchmarks/fixtures/payments.ts:37-61`
**Mistake**: `stripe.charges.create` is called with no idempotency key, and it's reachable both from `handleWebhook` (Stripe webhooks are at-least-once by design — redelivery is normal, not edge-case) and from the function's own internal retry (`retry: true` calls itself again with a fresh network round-trip, no key tying the two attempts together).
**Consequence**: ordinary webhook redelivery or a transient network blip on the retry path double-charges the customer. Worse, on failure the catch block returns `null` with no logging and no rethrow — `handleWebhook` never checks the return, so a *failed* charge for an invoice Stripe considers paid vanishes silently too.
**Today**: None (retry flag is the opposite of a device — it's rung 0 wearing a costume, per M2 in the hazard catalog).
**Device**: require an `idempotencyKey` parameter, pass it as `stripe.charges.create(..., { idempotencyKey })`, derive it from the Stripe event ID in `handleWebhook`. → **Control**. Also stop swallowing the error — log and rethrow, don't return `null`.

## 3. `transfer` — swappable accounts, no transaction, check-then-act race — Money/Data corruption · Silent
**Where**: `benchmarks/fixtures/payments.ts:17-35`
**Mistake**: `fromAccount`/`toAccount` are adjacent same-type strings (swap compiles and passes review). Separately: balance is read, then two `update` calls happen outside a transaction — a crash or two concurrent transfers between the read and the writes can leave money created or destroyed, and nothing stops a second concurrent call from reading the same stale balance and also passing the funds check.
**Consequence**: ledger goes out of balance, silently, only found on reconciliation.
**Today**: None.
**Device**: wrap both updates in a single DB transaction with a `WHERE balance >= amount` conditional update (turns the race into an atomic compare-and-swap) → **Control** for the transaction/race. For the swap: branded `AccountId` type distinguishing nothing structurally (both are accounts) — realistically here named/keyword args are the practical fix → **Warning**.

## 4. `purgeCanceledAccounts()` deletes everything by default — Irreversible data loss · One missing argument
**Where**: `benchmarks/fixtures/payments.ts:80-91`
**Mistake**: `olderThan` is optional; omit it and `cutoff = new Date()` — "purge accounts canceled before right now," i.e. every canceled account, ever. Calling `purgeCanceledAccounts()` with no thought at all is the most destructive possible call.
**Consequence**: irreversible bulk delete, and the reported "doomed" count comes from a separate `findMany` — a different query than the raw `DELETE` — so under concurrent writes the count and the actual deleted rows can disagree, meaning even the audit trail on this delete can't be trusted.
**Today**: None.
**Device**: make the cutoff required (no default that means "everything"), and derive the `DELETE` from the same predicate/IDs the count came from rather than a second raw-SQL query → **Control**.

## 5. `updateSubscription` writes status the feature-flip switch doesn't handle — Silent inconsistency · Any new/other status
**Where**: `benchmarks/fixtures/payments.ts:67-78`
**Mistake**: `status: string` (stringly typed) is written to the DB unconditionally, then a `switch` with only `"active"`/`"canceled"` cases and no `default` decides whether to flip features. Any other legitimate Stripe subscription status (`past_due`, `trialing`, `paused`, ...) updates the DB but silently skips the enable/disable step.
**Consequence**: a customer's billing status and their actual feature access drift apart with no error anywhere.
**Today**: None.
**Device**: a literal union for status with an `assertNever` default arm, so a status the switch doesn't handle is a compile error, not a silent no-op → **Control**.

## Set aside
- `applyDiscount(price, percentOff)` — money as a bare `number`, and `percentOff` isn't bounded to 0–100, so a value like 150 flips the discount into a price *increase*. Real, but needs a bad input value rather than firing on ordinary use — lower priority than the above.

Want me to apply any of these, or write this up to `docs/poka-yoke/audit-2026-08-22.md` first?