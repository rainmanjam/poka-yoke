# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts`

**Verdict:** Do not ship this as billing code. It can double-charge customers, let arbitrary input initiate charges, corrupt balances, and delete accounts broadly.

1. **`invoice.paid` issues another charge** — irreversible money movement / easy  
   **Where:** [payments.ts:93](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:93)  
   **Mistake:** Treating a successful-payment webhook as an instruction to collect payment again. Stripe defines `invoice.paid` as a successful payment attempt (or an out-of-band payment), so line 98 is a likely duplicate charge. [Stripe event reference](https://docs.stripe.com/api/events/types)  
   **Today:** None. The JSON is also neither signature-verified nor schema-validated.  
   **Device:** Verify the Stripe signature at the HTTP boundary; accept only a parsed, verified event; record `event.id` under a unique constraint before handling it. **Control.**

2. **Ambiguous failure retries a charge without idempotency** — irreversible money movement / easy  
   **Where:** [payments.ts:37](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:37)  
   **Mistake:** Retrying after a timeout where Stripe may already have created the first charge.  
   **Consequence:** The recursive retry can bill twice, while the catch-all `return null` makes the outcome look like an ordinary failure.  
   **Today:** None.  
   **Device:** Require an idempotency key, send it to Stripe, and persist `(customer, key, request hash, result)` behind a unique constraint so retries replay the original result. **Control.**

3. **Transfers are non-atomic and accept invalid money** — balance corruption / easy  
   **Where:** [payments.ts:17](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:17)  
   **Mistake:** Pass a negative amount, transfer an account to itself, race two transfers, use a missing destination, or mix currencies.  
   **Consequence:** A self-transfer credits the account by `amount`; a failed second update can leave the source debited; concurrent reads can overspend or lose updates. `number` also permits fractional/unsafe monetary values.  
   **Today:** None.  
   **Device:** Use validated positive minor-unit `Money` with currency; reject identical source/destination; debit conditionally (`balance >= amount`) and credit inside one DB transaction; add database non-negative/currency constraints. **Control.**

4. **Account purge has a dangerous implicit scope** — irreversible deletion / easy  
   **Where:** [payments.ts:80](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:80)  
   **Mistake:** Call `purgeCanceledAccounts()` without considering the cutoff.  
   **Consequence:** It deletes every canceled account older than “now,” with no preview, cap, or recoverability. It also uses interpolated `executeRawUnsafe` and reports a separately-read count that can differ from what was deleted.  
   **Today:** None.  
   **Device:** Require an explicit retention cutoff, parameterize the query, dry-run/count by default, and refuse operations above a cap unless a distinct explicit override is supplied; prefer soft deletion. **Control.**

5. **Subscription status can be arbitrary and side effects can split from state** — silent entitlement errors / easy  
   **Where:** [payments.ts:67](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:67)  
   **Mistake:** Pass `"active "` or a new status, or have `enableFeatures` fail after the database update.  
   **Consequence:** Invalid statuses persist silently; features may not match subscription state.  
   **Today:** None.  
   **Device:** Parse to a closed status union, make transitions go through one state-machine function with exhaustive handling, and publish feature changes through a transactional outbox. **Control** for valid states; durable delivery needs the outbox.

6. **Receipt failures disappear** — missing customer communication / silent  
   **Where:** [payments.ts:51](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:51)  
   **Mistake:** Fire-and-forget the receipt email.  
   **Consequence:** Rejections and process shutdown can silently lose receipts.  
   **Today:** None.  
   **Device:** Persist a receipt job/outbox record and deliver it with retry and observability. A `no-floating-promises` rule is only a **Warning** and would be bypassed by `void`.

Also worth fixing: `applyDiscount` permits negative or over-100% discounts and uses bare numbers for money; `currency = "usd"` hides a billing decision; and `WEBHOOK_TIMEOUT` is read but never used.

One contextual warning: the file explicitly labels itself a deliberately hazard-rich eval fixture ([payments.ts:1](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/payments.ts:1)). If this repository ships production artifacts, add a packaging/build boundary that makes importing `benchmarks/fixtures/**` from deployable code impossible.