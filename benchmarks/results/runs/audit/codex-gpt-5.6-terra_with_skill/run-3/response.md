Do not ship this as billing code. It is also explicitly a deliberately hazard-rich benchmark fixture, but if these patterns exist in the real module, they’re ship blockers.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts`

**Verdict:** an unauthenticated webhook can initiate charges, retry logic can double-charge, and transfers/deletes can leave irreversible inconsistent state.

1. **Forging or replaying a webhook to charge a customer** — money movement / easy  
   **Where:** [payments.ts:93](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:93)  
   **Mistake:** send arbitrary JSON—or replay a legitimate event—to this handler.  
   **Consequence:** it trusts `event.data.customer` and `amount`, then creates a charge. There is no Stripe signature verification, schema validation, or idempotency.  
   **Today:** None.  
   **Device:** verify the Stripe signature against the raw request body, schema-parse the verified event, and dedupe on the provider event ID before processing → **Control**.

2. **Retrying a charge after an ambiguous Stripe failure** — money movement / easy  
   **Where:** [payments.ts:37](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:37)  
   **Mistake:** retry after a timeout or connection failure. Stripe may have charged successfully even though this process never received the response.  
   **Consequence:** [the recursive retry](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:56) issues a second charge.  
   **Today:** None.  
   **Device:** require an `IdempotencyKey`, send it to Stripe, reserve it in a database row with a unique `(customer, key)` constraint, bind it to the request payload, and replay the stored result for duplicates → **Control**.

3. **Making a transfer that only half completes—or loses concurrent updates** — money movement / easy  
   **Where:** [payments.ts:17](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:17)  
   **Mistake:** transfer to a missing account, hit an error between the two updates, or submit transfers concurrently.  
   **Consequence:** the debit and credit are separate writes; money can leave one account without reaching the other. The read-then-write balance update also races. `from!`/`to!` turn a missing account into a late generic crash.  
   **Today:** None.  
   **Device:** use one database transaction with `findUniqueOrThrow`, conditional atomic debit (`balance >= amount`), atomic credit, positive/safe-integer validation, and a database `CHECK (balance >= 0)` → **Control**. Brand `FromAccountId` and `ToAccountId` so callers cannot silently swap the two string arguments.

4. **Deleting every canceled account by omitting an argument** — irreversible deletion / easy  
   **Where:** [payments.ts:80](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:80)  
   **Mistake:** call `purgeCanceledAccounts()` without a cutoff.  
   **Consequence:** the default is “now,” which matches effectively every previously canceled account. The count query and unsafe raw delete are separate operations, with no cap or transaction.  
   **Today:** None.  
   **Device:** make the cutoff explicit, delete the exact selected IDs in a transaction, enforce a maximum affected-row count, and prefer soft deletion/dry-run behavior. Replace `$executeRawUnsafe` with parameterized ORM/SQL → **Control**.

5. **Treating an uncertain charge as a clean non-charge** — silent wrong result / easy  
   **Where:** [payments.ts:55](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:55)  
   **Mistake:** any Stripe error or local timeout reaches the catch block.  
   **Consequence:** it returns `null`, erasing whether the payment was declined, failed, or actually succeeded remotely. Callers can proceed on a plausible but false result.  
   **Today:** None.  
   **Device:** return a typed outcome that distinguishes declined, definitely failed, and indeterminate; retain the idempotency record and reconcile indeterminate Stripe outcomes rather than retrying blindly → **Warning** (the idempotent charge design above removes the costly duplicate-charge consequence).

6. **Passing fractional, unsafe, or wrong-currency money values** — silent financial corruption / easy  
   **Where:** [payments.ts:12](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:12), [payments.ts:63](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:63)  
   **Mistake:** pass `12.5`, `NaN`, an unsafe integer, or a value in the wrong currency.  
   **Consequence:** JavaScript `number` is binary floating point; `price` and balances can accrue rounding errors, while `amountCents` is not verified as an integer minor-unit amount.  
   **Today:** None.  
   **Device:** parse bounded safe integer minor units at the boundary and use a branded `Money`/currency-aware value type; use decimal arithmetic where fractional currency is truly needed → **Control**.

7. **Adding or misspelling a subscription state without feature handling** — silent state drift / easy  
   **Where:** [payments.ts:67](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:67)  
   **Mistake:** call `updateSubscription(id, "past_due")`, typo a status, or add a new status later.  
   **Consequence:** the database status changes but neither feature action runs; a failure after the database update also leaves status and entitlements inconsistent.  
   **Today:** None.  
   **Device:** use a closed `SubscriptionStatus` union plus `assertNever` exhaustiveness, route changes through a single legal-transition function, and persist an outbox event with the state update for idempotent entitlement changes → **Control**.

## Set aside

- [Positional booleans](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:41) make `sendReceipt` and `retry` easy to invert; use named options or separate operations.
- [The receipt email](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:52) is fire-and-forget, so failures disappear; use an outbox/worker or await it when delivery is required.
- [Webhook timeout config](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:95) is read per request and unused; validate configuration at startup.

I made no changes.