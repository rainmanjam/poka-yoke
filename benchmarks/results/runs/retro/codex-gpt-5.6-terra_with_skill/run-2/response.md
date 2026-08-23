No. The “recent charge with the same amount” check is a heuristic, not a control:

- It can block legitimate repeat purchases with the same amount.
- Two redeliveries can both check before either charge exists (a race).
- A delay beyond the “recent” window can charge again.
- It does not give Stripe a stable identity for “this is the same payment attempt.”

Your incident, stated plainly:

- **Defect:** 340 customers were charged twice.
- **Mistake:** a redelivered message issued a second payment request after the first request’s result was unknown.
- **Hazard:** the system permits a payment attempt to reach Stripe without a durable, required idempotency identity shared by every retry.

The fix should be a control:

1. Create a durable `payment_attempt` before enqueueing work, with an immutable ID and a database uniqueness constraint matching one intended payment (for example, `order_id + attempt_number`).
2. Derive the Stripe idempotency key from that ID and require it in the payment gateway interface—no worker or caller may generate a new key per delivery.
3. Persist the Stripe object ID and request fingerprint. On timeout, retry the *identical* request with the same key; do not infer intent from prior charges or create a new attempt.
4. Treat duplicate queue delivery as normal. It must resolve to the same payment attempt, even concurrently.
5. Keep your own durable record longer than Stripe’s idempotency window. Stripe’s API v1 keys can be pruned after 24 hours, so its cache alone is not your long-term correctness boundary. [Stripe idempotent-request docs](https://docs.stripe.com/api/idempotent_requests?lang=curl)

Stripe explicitly supports retrying a failed/unknown `POST` safely when it uses the same idempotency key, returning the initial result instead of creating another object. [Stripe error-handling guidance](https://docs.stripe.com/error-low-level)

The amount-based check can remain temporarily as a **detection/circuit-breaker**—ideally alerting and holding ambiguous attempts for reconciliation—but it should not decide whether to charge.

Before calling this resolved, prove the device fails:

- Simulate Stripe successfully creating a charge while the worker times out before receiving the response; redeliver the message and assert exactly one Stripe charge.
- Deliver the same message concurrently to two workers; assert one charge.
- Assert a payment call without a durable attempt ID/idempotency key is rejected by the payment gateway wrapper.
- Sweep every other Stripe `POST` path—charges, PaymentIntent creation/confirmation, refunds, subscriptions—for the same optional-or-generated-per-retry key hazard.

Given this is the second incident, I would not close it on the current change. The required device is “one intended payment → one durable payment-attempt ID → one Stripe idempotency key,” not “avoid recently matching amounts.”