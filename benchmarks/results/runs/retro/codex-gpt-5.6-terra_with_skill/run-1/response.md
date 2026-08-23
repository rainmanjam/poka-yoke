No. The amount-based lookup is a race-prone heuristic: two workers can both see no recent charge and then charge; it can also block two legitimate payments of the same amount. It is at best a **Warning**, not a control.

| Item | Finding |
|---|---|
| Defect | 340 customers charged twice |
| Mistake | A redelivered job made a new Stripe charge after an outcome-unknown timeout |
| Hazard | The payment operation has no durable, unique identity carried across retries |

Install the control at the payment-operation boundary:

1. Create one durable `payment_attempt` per business obligation (e.g., order or invoice installment), with a database uniqueness constraint on that obligation and on its idempotency key. Store amount, currency, payload hash, status, and Stripe object ID.
2. Generate the Stripe idempotency key once when that attempt is created—never in the worker—and require it for every charge/create call. Replays must use the exact same key and payload.
3. Make the worker stateful: atomically claim or retrieve the existing attempt; on a timeout, mark it `unknown`/`reconciling`, then retrieve/replay the same Stripe operation or wait for the webhook. Do not create a fresh charge.
4. Prefer a stored PaymentIntent and reuse its ID for the same purchase, rather than creating another payment object. Stripe explicitly recommends associating the PaymentIntent and idempotency key with the cart/session. [Stripe Payment Intents guide](https://docs.stripe.com/payments/payment-intents)
5. Keep your database record longer than Stripe’s idempotency retention. Stripe may prune keys after at least 24 hours, so the application ledger must remain the durable source of “has this obligation already been paid?” [Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests)

Also add detection, but don’t confuse it with the fix:

- A concurrency test: two deliveries of one payment attempt produce one provider payment.
- A timeout-after-Stripe-accepts test: retry uses the same key and resolves to the original result.
- A reconciliation alert for attempts stuck `unknown` and for more than one successful provider charge per business obligation.
- Sweep every money-moving worker and API path for retries that generate a new idempotency key or accept none.

The key invariant is: **one business payment obligation maps to one durable payment attempt and one provider operation identity**. Queue delivery is allowed to be at-least-once; charging is not.