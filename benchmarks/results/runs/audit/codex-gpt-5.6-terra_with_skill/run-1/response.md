# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-22

**Verdict:** Do not ship this as a real billing module: a replayed or forged webhook can create charges, and ordinary concurrency can create or lose money.

The fixture header confirms these hazards are deliberate; the detector found 9 mechanical signals, and the highest-risk issues need architectural controls.

## Findings

### 1. A webhook can cause arbitrary or repeated charges — money movement / easy

**Where:** [payments.ts:93](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:93)

**Mistake:** Send a forged event, or process Stripe’s normal webhook redelivery, as though it were a new command to charge.

**Consequence:** `JSON.parse` accepts untrusted data, no Stripe signature is verified, and no event ID is deduplicated. An `invoice.paid` event also normally means payment has already succeeded—charging again here is especially suspect. This can silently double-charge customers.

**Today:** None.

**Device:** Verify the provider signature and parse against an event schema at the boundary; persist the provider event ID in the same transaction as processing under a unique constraint; require the downstream charge idempotency key. → **Control**

### 2. Transfers are non-atomic, unauthenticated retries can create money — money movement / easy

**Where:** [payments.ts:17](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:17)

**Mistake:** Run two transfers from the same account concurrently, retry one after an uncertain failure, or let the second update fail.

**Consequence:** Both callers can pass the stale balance check; each recipient may be credited while only one debit “wins.” A failure after the debit loses money. No idempotency key prevents a retried transfer from running again.

**Today:** None.

**Device:** Make transfer a single database transaction: conditional debit (`balance >= amount`), matching credit, and a required transfer idempotency key protected by a unique database constraint. Reject self-transfers, non-positive amounts, and currency mismatches inside that transaction. → **Control**

### 3. Retrying a charge after an unknown Stripe outcome can double-charge — money movement / easy

**Where:** [payments.ts:37](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:37)

**Mistake:** Set `retry` after a timeout where Stripe may already have created the charge.

**Consequence:** The catch-all recursively calls Stripe again without an idempotency key. It then returns `null` for all remaining failures, turning an uncertain financial outcome into a plausible “no charge” result.

**Today:** None.

**Device:** Require an idempotency key, pass it to Stripe, persist/replay the result keyed to a request-payload fingerprint, and propagate typed failures rather than returning `null`. Remove the positional retry boolean. → **Control**

### 4. The transfer interface permits swapped accounts and invalid monetary values — silent corruption / easy

**Where:** [payments.ts:17](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:17)

**Mistake:** Reverse the two string account IDs, pass a negative/zero amount, or transfer across currencies.

**Consequence:** It compiles and looks reasonable in review. In particular, a negative transfer reverses the economic effect. Passing the same account can increase its balance because both updates use the originally read balance.

**Today:** None.

**Device:** Use a named command object with validated, branded IDs and a `Money` value; reject self-transfers and require a positive amount. Distinguish source and destination at the API boundary if positional calls remain. → **Control** for validity; named fields are **Warning** for accidental reversal.

### 5. Currency is represented as floating-point `number` — silent reconciliation failures / easy

**Where:** [payments.ts:12](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:12), [payments.ts:63](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:63)

**Mistake:** Use a fractional value or mix values whose units/currencies differ.

**Consequence:** Floating-point rounding leaks into balances and discounts; `amountCents` has a useful name but is still an unconstrained number and is detached from `currency`.

**Today:** None.

**Device:** Store integer minor units (or decimal values) in a `Money` type carrying an allowed currency; validate discount percentage as an integer/range. → **Control**

### 6. Subscription state can claim success before its side effect succeeds — entitlement drift / easy

**Where:** [payments.ts:67](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:67)

**Mistake:** Set any string as `status`, or have feature enablement fail after the database write.

**Consequence:** Unknown statuses silently do nothing, and the database can say “active” while access was never enabled. There is no enforced transition graph.

**Today:** None.

**Device:** Use a closed status union plus exhaustive handling; route changes through one transition function that validates the prior state and writes an outbox record transactionally for entitlement updates. → **Control**

### 7. Omitting a purge argument permanently deletes every canceled account before now — irreversible loss / easy

**Where:** [payments.ts:80](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:80)

**Mistake:** Call `purgeCanceledAccounts()` without a cutoff.

**Consequence:** The default selects all historical canceled accounts, then permanently deletes them without a cap or recovery path. The separately queried `doomed.length` can disagree with what was actually deleted. `$executeRawUnsafe` is an unnecessary injection footgun.

**Today:** None.

**Device:** Require an explicit, validated retention cutoff; parameterize the query; dry-run and cap affected rows by default; use soft deletion where the domain permits. → **Control**

### 8. Receipt delivery failures disappear — wrong customer-facing outcome / easy

**Where:** [payments.ts:52](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:52)

**Mistake:** Fire the receipt promise and assume it completed.

**Consequence:** A successful charge can return while receipt delivery fails or is abandoned on shutdown, with no recovery signal.

**Today:** None.

**Device:** Write a receipt event to a transactional outbox and deliver it with durable retries; at minimum, reject unhandled promises through linting. → **Control** with an outbox; lint alone is **Warning**.

## Set aside

- [payments.ts:21](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:21) uses non-null assertions, so missing accounts fail as a generic runtime exception rather than a domain error.
- [payments.ts:95](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:95) reads `WEBHOOK_TIMEOUT` per request and never uses it; configuration would not fail at deploy time.
- [payments.ts:40](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:40) defaults currency and uses positional booleans, hiding billing decisions at call sites.