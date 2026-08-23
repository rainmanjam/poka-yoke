# Code Review: `payments.ts`

## Summary

Not ship-ready. The file has critical paths that can create or move money incorrectly, double-charge on retries, and let an unverified webhook initiate charges.

## Critical — fix before merge

- **[CRT-1] Transfers are not atomic** — [payments.ts:17](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:17)  
  Two concurrent transfers can both read the same balance and overspend it; if the second update fails, money is debited without being credited.  
  **Device:** one database transaction with a conditional atomic debit (`balance >= amount`) followed by the credit; roll back both on any failure.

- **[CRT-2] Transfer inputs can mint money** — [payments.ts:21](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:21)  
  A negative `amount` passes the insufficient-funds check, raises the source balance, and lowers the destination balance. Passing the same account as both endpoints also produces an incorrect final balance.  
  **Device:** accept a validated positive integer `AmountCents`, reject `from === to`, and enforce these invariants at the database boundary too.

- **[CRT-3] Retry can double-charge** — [payments.ts:45](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:45)  
  If Stripe completes the charge but the response times out, the catch/retry at line 57 submits a second charge.  
  **Device:** require an idempotency key on every charge request, persist it with a unique database constraint, and pass it to Stripe on every retry.

- **[CRT-4] Webhook payloads are neither authenticated nor validated** — [payments.ts:93](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:93)  
  Any caller able to reach this function can supply JSON shaped like `invoice.paid` and cause a charge. Even legitimate webhook delivery retries can repeat the side effect.  
  **Device:** verify Stripe’s signature using the raw request body, schema-parse the verified event, and deduplicate on Stripe event ID before processing. Reconsider whether `invoice.paid` should ever create another charge.

## Major — should fix before merge

- **[MAJ-1] `fromAccount` and `toAccount` can be silently swapped** — [payments.ts:17](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:17)  
  **Mistake:** call `transfer(destinationId, sourceId, amount)`. Both are `string`, so TypeScript accepts it and money moves in the wrong direction.  
  **Device:** use named arguments plus distinct branded `SourceAccountId` / `DestinationAccountId` types.

- **[MAJ-2] Money is represented as JavaScript `number`** — [payments.ts:12](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:12)  
  Balances and discounts are vulnerable to floating-point rounding and non-integer inputs.  
  **Device:** store and operate on integer minor units (or `bigint` / a decimal DB type), with a branded `AmountCents` type.

- **[MAJ-3] Charge failures are hidden** — [payments.ts:55](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:55)  
  Returning `null` erases the Stripe failure and makes an uncharged customer indistinguishable from a normal nullable result. The un-awaited receipt email can also fail invisibly.  
  **Device:** return a typed success/failure result or rethrow a classified error; enqueue receipts through a durable outbox with retries and monitoring.

- **[MAJ-4] Unsafe interpolated SQL in account purge** — [payments.ts:86](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:86)  
  The current `Date` conversion limits immediate exploitability, but `$executeRawUnsafe` makes SQL construction a future injection footgun. The read-before-delete count can also diverge from what was deleted.  
  **Device:** use a parameterized delete / ORM delete-many and return its affected-row count. Make the deletion a deliberate retention workflow or soft-delete rather than an irreversible helper.

- **[MAJ-5] Subscription states are open-ended and effects can drift** — [payments.ts:67](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:67)  
  `status: string` permits arbitrary values; `past_due` or a future status updates the database while doing no feature work. If `enableFeatures`/`disableFeatures` fails, DB state and entitlements disagree.  
  **Device:** model subscription states as a discriminated union with an exhaustive `never` switch, and use an outbox/reconciliation process for entitlement changes.

## Positive

- The insufficient-balance guard and the attempt to centralize charging are useful starting points; they need stronger invariants around them rather than more caller discipline.

## Suggested tests

- Two simultaneous transfers from the same account cannot overdraft; a forced failure leaves both balances unchanged.
- Negative, zero, fractional, overflowing, and same-account transfers are rejected.
- A Stripe timeout after successful processing results in exactly one charge for one idempotency key.
- Invalid, unsigned, duplicate, and malformed webhook events cannot trigger a charge.
- Every subscription status has defined entitlement behavior; an entitlement failure is recoverable and observable.
- Purge returns exactly the number deleted and cannot interpolate executable SQL.

No files were modified.