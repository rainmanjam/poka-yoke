# Code Review: `benchmarks/fixtures/payments.ts`

## Summary

Block shipment. The most serious issue is that an `invoice.paid` webhook charges the customer again; retries and webhook redelivery make double-charges likely.

## Critical

- **[CRT-1] A paid-invoice webhook creates another charge** — [payments.ts:97](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:97)  
  Someone receiving a legitimate, at-least-once-delivered `invoice.paid` event will call `chargeCustomer` again. Verify Stripe’s signature on the raw body, deduplicate the provider event ID in the database, and mark/reconcile the invoice as paid—do not charge in response to `invoice.paid`.

- **[CRT-2] Payment retry can double-charge** — [payments.ts:45](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:45)  
  A network timeout can occur after Stripe accepts the first request but before this process receives the response; the recursive retry at line 57 then creates a second charge. Require a caller-supplied idempotency key, persist it with a unique constraint, and send the same key to Stripe on every retry. Treat ambiguous outcomes as pending/reconcilable, not safe to repeat.

- **[CRT-3] Transfers can create money or leave accounts inconsistent** — [payments.ts:17](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:17)  
  There is no transaction or atomic conditional debit. Concurrent transfers can both pass the balance check; a failure after the debit but before the credit loses money. A transfer to the same account credits the account (`from` write is overwritten by the `to` write). Negative amounts reverse the transfer. Use one database transaction with integer minor units, reject non-positive amounts/self-transfers/currency mismatches, and make the debit conditional on sufficient balance.

## Major

- **[MAJ-1] Errors are silently converted to `null`** — [payments.ts:55](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:55)  
  A caller cannot distinguish a decline, invalid request, Stripe outage, or an indeterminate charged state. Return a typed outcome or rethrow classified errors; log and reconcile indeterminate payment attempts.

- **[MAJ-2] Webhook input is neither authenticated nor validated** — [payments.ts:93](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:93)  
  Anyone who can reach this handler can submit a JSON body that triggers billing. `JSON.parse` also yields untrusted `any`. Verify the provider signature before parsing, validate a narrow event schema, and persist processed event IDs uniquely.

- **[MAJ-3] Account IDs are swappable, and missing accounts crash** — [payments.ts:17](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:17)  
  `fromAccount` and `toAccount` are indistinguishable strings, so a caller can reverse them without a type error. The non-null assertions at lines 21/27/31 turn missing accounts into runtime failures. Use branded ID types and explicit not-found handling.

- **[MAJ-4] Money uses JavaScript floating-point numbers** — [payments.ts:12](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:12)  
  Balances, amounts, and discounts can accumulate rounding errors. Store and transfer integer minor units (or a decimal type), always coupled to currency; define rounding and bounds for discounts.

- **[MAJ-5] Raw SQL is unnecessarily unsafe** — [payments.ts:86](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:86)  
  Interpolating values into `executeRawUnsafe` establishes an injection-prone pattern. Use a parameterized query/ORM delete. Also make the selection/count and deletion transactional if the returned count is meant to describe what was deleted.

- **[MAJ-6] Subscription state accepts arbitrary strings** — [payments.ts:67](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:67)  
  Someone can persist `"past_due"` or a typo, but neither feature action runs. A feature-operation failure also leaves the DB status changed. Model status as a discriminated union with an exhaustive transition function; coordinate state changes and side effects through a transaction/outbox.

## Minor

- **[MIN-1] Receipt email failures are discarded** — [payments.ts:52](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:52)  
  Use an outbox/job with retries and monitoring instead of an unobserved promise.

- **[MIN-2] `WEBHOOK_TIMEOUT` is unused** — [payments.ts:95](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:95)  
  Parse and validate configuration at startup, then actually enforce a timeout if intended.

## Positive

- The delete is visibly scoped to canceled accounts and a cutoff, which makes its intended blast radius clear. Parameterization and transactional semantics are still needed.

## Suggested tests

- Redeliver the same signed `invoice.paid` event twice; assert no new charge is created.
- Simulate Stripe accepting a charge then timing out; retry with the same idempotency key and assert one charge.
- Run concurrent transfers against one balance; assert no overdraft, money creation, or partial transfer.
- Assert negative amounts, self-transfers, missing accounts, currency mismatches, invalid statuses, and malformed/unsigned webhooks fail.