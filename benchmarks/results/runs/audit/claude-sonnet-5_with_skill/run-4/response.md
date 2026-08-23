Scope: `benchmarks/fixtures/payments.ts` (105 lines, 6 exported functions), audited directly since you named the file. Skipped the diff-based detector since the whole file is in scope regardless of what's uncommitted.

# Poka-Yoke Audit — benchmarks/fixtures/payments.ts — 2026-08-22

**Verdict**: the webhook handler will execute an arbitrary Stripe charge for anyone who can POST to it — no signature verification — and that's before you even get to the two ways this module can double-charge a real customer.

## Findings

### 1. Webhook charges are triggered with no signature verification — Security bypass/money movement, trivial
**Where**: `payments.ts:93-100`
**Mistake**: `handleWebhook` calls `JSON.parse(body)` and acts on `event.type`/`event.data` directly. Nothing checks the `Stripe-Signature` header against your webhook secret.
**Consequence**: anyone who discovers the endpoint URL can POST `{"type":"invoice.paid","data":{"customer":"cus_victim","amount":999999}}` and it will call `chargeCustomer` for real. Silent — looks like a normal webhook delivery.
**Today**: None.
**Device**: `stripe.webhooks.constructEvent(body, sig, secret)` — throws on an invalid/missing signature. **Control.**

### 2. Charges are retried and re-delivered with no idempotency key — Money movement, silent, no malice required
**Where**: `payments.ts:37-61` (retry path), `93-98` (webhook)
**Mistake**: `chargeCustomer`'s own retry (`if (retry) return chargeCustomer(...)`) resubmits to Stripe with no idempotency key, so a charge that actually succeeded but timed out on the response gets charged twice. Separately, Stripe redelivers webhooks at-least-once — `handleWebhook` has no event-ID dedup, so a redelivered `invoice.paid` charges the customer again.
**Consequence**: duplicate customer charges — the same class of incident called out in this repo's own memory of a past double-charge incident. Fully silent; both charges look successful.
**Today**: None.
**Device**: pass a required idempotency key to `stripe.charges.create` (e.g. derived from invoice/event ID), and record processed webhook event IDs with a unique constraint so a replay is rejected by the DB, not by hope. **Control.**

### 3. `transfer` has no transaction, no amount validation, and swappable account IDs — Money movement/data corruption, silent
**Where**: `payments.ts:17-35`
**Mistake**: three separate hazards stacked in one function:
- `amount` isn't checked for being positive — call `transfer(a, b, -100)` and it passes the balance check (`from.balance < -100` is false) and *moves money backwards*, crediting `from` and debiting `to`.
- The two `db.accounts.update` calls aren't wrapped in a transaction — if the second update fails (network blip, connection drop), money vanishes from `from` and never lands in `to`.
- `fromAccount`/`toAccount` are adjacent same-typed strings — a caller can swap them and it still compiles and runs.
**Consequence**: silent money creation/destruction, or a plausible-looking transfer that actually reverses.
**Today**: None (the `!` non-null assertions on line 21/27/31 would only save you from a *missing* account, and even then by crashing, not by explaining what happened).
**Device**: validate `amount > 0` at the boundary; wrap both updates in a DB transaction; brand the account ID types (`SourceAccountId`/`DestinationAccountId`) so a swap doesn't typecheck. **Control** for all three.

### 4. `purgeCanceledAccounts` defaults to deleting everything, via raw SQL — Irreversible data loss, one careless call
**Where**: `payments.ts:80-91`
**Mistake**: `olderThan ?? new Date()` means calling `purgeCanceledAccounts()` with no argument — the natural-looking call — deletes **every** canceled account, not just old ones; the default maximizes blast radius instead of minimizing it. The actual delete goes through `$executeRawUnsafe` with a string-interpolated timestamp, bypassing the query builder's protections. It also runs as two independent statements (`findMany` then raw `DELETE`) with no transaction, so the returned count can silently disagree with what was actually deleted under concurrent cancellations.
**Consequence**: an engineer calling this expecting "clean up stale canceled accounts" instead purges the whole cohort, irreversibly.
**Today**: None.
**Device**: require `olderThan` (no default), use the parameterized query builder instead of `executeRawUnsafe`, and wrap count+delete in a transaction. **Control.**

### 5. `updateSubscription`'s switch silently drops unknown statuses — Silent state drift
**Where**: `payments.ts:67-78`
**Mistake**: the DB write happens unconditionally, then a `switch` with only `"active"`/`"canceled"` and no `default` decides feature flags. Any other real Stripe status (`past_due`, `trialing`, `paused`, `unpaid`, …) updates the DB but silently does nothing to features — no error, no log.
**Consequence**: subscription status and entitlement state drift apart with no signal, discovered only when a customer complains.
**Today**: None.
**Device**: exhaustive switch with an `assertNever` default arm (forces a compile error when a new status is handled elsewhere but not here), and put the DB write and feature toggle in the same transaction. **Control.**

### 6. `chargeCustomer` swallows the actual error — Silent failure
**Where**: `payments.ts:55-60`
**Mistake**: `catch (e)` never inspects or logs `e`; on non-retry it just `return null`. A declined card, an invalid customer ID, and a Stripe outage are all indistinguishable from each other and from "nothing happened."
**Consequence**: callers (like `handleWebhook`) can't tell whether to alert, retry, or ignore — they get `null` either way.
**Today**: None.
**Device**: log/report the specific Stripe error and rethrow a typed error, or return a discriminated result (`{ok: false, reason}`) instead of `null`. **Control** for the discriminated union.

## Set aside
- `chargeCustomer`'s `sendReceipt`/`retry` boolean flags (C2) — real footgun but dwarfed by the idempotency issue on the same function; fix both at once.
- `applyDiscount` doing float arithmetic on money with no bounds check on `percentOff` — worth fixing but low blast radius relative to the above.
- `void sendReceiptEmail(...)` fire-and-forget (M6) — an unhandled rejection risk, minor next to the charge-path issues.

Want me to propose the actual diffs for any of these? #1 and #2 (webhook signature + idempotency) are the ones I'd fix before shipping regardless of what else waits.