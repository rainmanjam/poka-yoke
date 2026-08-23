No. The “recent charge with the same amount” check is not a sufficient safeguard. It can race—two deliveries can both check before either charge exists—and it can block legitimate same-amount purchases. Keep it only as an anomaly signal, not as the payment gate.

**Retro**

- **Defect:** 340 customers were charged twice.
- **Mistake:** a redelivered queue message issued a new payment after an ambiguous Stripe timeout.
- **Hazard:** the worker can invoke a non-idempotent external payment effect without a durable, unique payment-operation identity.

The queue behaved normally: at-least-once delivery means duplicates are expected. The system needs to converge duplicates to one payment.

Install a control-level device:

1. Create one durable `payment_operation` per business action—e.g. `(order_id, attempt_number)`—with a database `UNIQUE` constraint and a request/payload hash.
2. Require that operation ID in the only internal function allowed to call Stripe; no optional idempotency parameter.
3. Derive/store one Stripe idempotency key for that operation and reuse it for every retry, including after a timeout. Stripe explicitly supports retrying indeterminate network failures with the *same* key and parameters. [Stripe error handling](https://docs.stripe.com/error-low-level) [Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests)
4. Persist the Stripe PaymentIntent/charge ID and operation state. If using PaymentIntents, reuse the same persisted PaymentIntent for the purchase rather than creating another. [Stripe Payment Intents guidance](https://docs.stripe.com/payments/payment-intents)
5. Make concurrent deliveries atomic: one worker owns the new operation; other deliveries return or wait for its recorded result. If the worker dies after Stripe accepts the request but before your DB update, the retry must send the same Stripe key—not create a new payment.
6. Treat a reused operation key with a different payload hash as an error, never as a silent replay.

Stripe’s idempotency retention alone is not your full guarantee—its API v1 keys may be pruned after 24 hours—so retain your own operation record for the full period that delayed/redelivered work could occur, ideally for the payment’s audit lifetime. [Stripe idempotency reference](https://docs.stripe.com/api/idempotent_requests)

Also add detection as a backstop, not the fix:

- Daily reconciliation: exactly one successful Stripe payment per payment operation; alert on any mismatch.
- A regression test that forces: Stripe accepts → response times out/lost → queue redelivers. Assert exactly one Stripe payment.
- A concurrency test with two workers handling the same message.
- A near-miss test: two distinct orders of the same amount must both charge successfully.

This is **Control** when the unique operation record and required Stripe key are enforced at the payment boundary. The current lookup is not: it leaves the check-then-charge race available, which is precisely why a second recurrence remains possible.