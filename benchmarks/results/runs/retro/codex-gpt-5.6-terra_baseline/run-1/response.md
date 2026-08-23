No. The “same recent amount” lookup is a temporary tripwire, not a payment-safety guarantee:

- It races: two workers can both look, see nothing, then both charge.
- It blocks legitimate equal-amount purchases by the same customer.
- It cannot distinguish retries from separate business transactions.
- It will fail again under delayed Stripe visibility, concurrent delivery, or a retry outside its lookback window.

The durable fix is idempotency tied to the business operation—not to a queue delivery or worker attempt.

1. Create one permanent `payment_operation` per order/invoice, with a unique database constraint on its business ID.
2. Persist a stable Stripe idempotency key and, preferably, the Stripe PaymentIntent ID on that operation *before* allowing retries.
3. Every redelivery retries the same PaymentIntent/request using the same idempotency key—never creates a new charge/payment intent.
4. On a timeout, treat the outcome as **unknown**, not failed: retrieve/reconcile the existing Stripe object, then retry the exact same request/key if appropriate.
5. Use Stripe webhooks plus periodic reconciliation to settle the local operation state; attach your operation ID in Stripe metadata for recovery/audit.

Stripe explicitly recommends idempotency keys for retry-safe POSTs and says a network timeout should be retried with the *same* key. Its PaymentIntents guidance also says to reuse the same PaymentIntent for an interrupted payment. [Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests?lang=curl), [Stripe advanced error handling](https://docs.stripe.com/error-low-level), [Stripe PaymentIntents](https://docs.stripe.com/payments/payment-intents)

For today: disable automatic queue retries for ambiguous payment outcomes and route those jobs to reconciliation/manual review until the above invariant is live. Keep the “same amount” check only as an alerting guardrail, never the authorization to charge or suppress a charge.

Because this is recurrence #2, prove the fix with fault-injection tests: force a timeout after Stripe accepts the request, simultaneous duplicate deliveries, worker crash before/after persisting state, and delayed webhooks. Each must show exactly one successful charge for one payment operation.