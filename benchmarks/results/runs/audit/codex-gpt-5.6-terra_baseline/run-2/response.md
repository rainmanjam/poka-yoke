# Code Review: payments.ts

## Summary

This is not a shipping billing module: its header explicitly labels it an intentionally hazard-rich benchmark fixture, and the repository scenario uses this exact prompt. Don’t “fix” this fixture before shipping—it would invalidate the benchmark. But if the real module resembles it, it needs rework before release.

## Critical

- **[CRT-1] Unsigned webhook can initiate charges** — [payments.ts:93](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:93)  
  Arbitrary JSON is parsed and used to call `chargeCustomer`; there is no Stripe signature verification, schema validation, or processed-event replay guard. A forged or redelivered event can charge a customer. Charging on `invoice.paid` is especially suspicious: that event represents an already-paid invoice.

- **[CRT-2] Transfers are non-atomic and race-prone** — [payments.ts:17](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:17)  
  Separate reads and updates allow concurrent transfers to pass the same balance check. A failure after the debit but before the credit destroys money. Missing destination accounts throw only after the source is debited. Use one database transaction with an atomic conditional debit and atomic credit.

- **[CRT-3] No-argument purge deletes all canceled accounts** — [payments.ts:80](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:80)  
  `purgeCanceledAccounts()` defaults to “before now,” i.e. every canceled account. It hard-deletes without a limit or confirmation, and returns the prior read count rather than the delete result.

## Major

- **[MAJ-1] Retrying can double-charge** — [payments.ts:44](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:44)  
  A timeout can occur after Stripe accepted the charge. Retrying without a stable business-operation idempotency key creates a second charge. Require an idempotency key and pass it to Stripe; additionally enforce uniqueness in your own charge ledger.

- **[MAJ-2] Failures are silently converted to `null`** — [payments.ts:55](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:55)  
  The caller cannot distinguish a decline, outage, timeout-after-success, or programming error. Propagate a typed failure and log/alert it; never let payment state be inferred from `null`.

- **[MAJ-3] Raw interpolated SQL** — [payments.ts:86](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:86)  
  `$executeRawUnsafe` embeds a runtime value in SQL. Even though TypeScript says `Date`, types do not validate runtime callers. Use the ORM delete API or a parameterized query.

- **[MAJ-4] Subscription side effects can silently be skipped** — [payments.ts:67](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:67)  
  `status` is an unrestricted string and the switch has no exhaustive/default failure. `"cancelled"` instead of `"canceled"` updates the DB but leaves paid features enabled. Use a status union/enum plus exhaustive handling, ideally with the DB update and entitlement change in one transaction/outbox flow.

- **[MAJ-5] Money and input constraints are absent** — [payments.ts:9](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:9)  
  Balances use JS `number`, which permits floating-point rounding. Negative transfer/charge values reverse the operation, fractional “cents” are accepted, currencies can be mixed, and discounts can exceed 100%. Store integer minor units (or a decimal type), validate positive integers and currency equality, and bound discounts to 0–100.

## Minor

- **[MIN-1] Swappable positional arguments** — [payments.ts:17](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:17)  
  `transfer(to, from, amount)` is valid TypeScript and moves money backwards. `chargeCustomer` also ends in two booleans. Prefer parameter objects and distinct/branded ID types.

- **[MIN-2] Receipt failures are dropped** — [payments.ts:52](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:52)  
  `void sendReceiptEmail(...)` makes a failed receipt invisible. Queue it durably or explicitly observe and report its rejection.

- **[MIN-3] Dead configuration** — [payments.ts:95](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:95)  
  `WEBHOOK_TIMEOUT` is read but never enforced, which makes it look like a control that doesn’t exist.

## Positive

- **[POS-1] The small functions make the dangerous boundaries easy to isolate** — e.g. [payments.ts:37](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:37). A real implementation can replace each boundary with a stricter API without a broad rewrite.

## Suggested tests

- Two concurrent transfers cannot overdraft or change total funds; nonexistent destination rolls back the debit.
- Replaying the same charge request/webhook returns the original charge and creates exactly one ledger entry.
- Forged, malformed, and duplicate webhook events are rejected.
- Bare purge is rejected; only a bounded, explicit cutoff can delete records.
- Negative/fractional amounts, mixed currencies, invalid statuses, and discounts outside 0–100 fail at the boundary.