No, that's not enough—and the session memory shows you've already identified why. The amount-based check has a **TOCTOU race**: between checking "did we charge $X recently?" and actually charging, another request could have slipped through. It's a patch, not a fix.

The proper solution is **idempotency keys**:

1. **Stripe side**: Every charge request includes a unique idempotency key tied to the order. Stripe deduplicates on that key. If the timeout fires and we retry, Stripe returns the original charge. This is the standard pattern—Stripe already handles it correctly.

2. **Database side**: Store the idempotency key (e.g., `order_id`) + the charge attempt. Add a unique constraint on `(order_id, stripe_charge_id)` or similar so a second attempt is caught at your edge before it even reaches Stripe.

3. **Queue-wide**: The memory notes you have other non-idempotent consumers (emails, webhooks, ledger, Stripe handler). Each one that mutates state needs idempotency keys to survive redelivery. Don't patch each one individually—solve the pattern.

The blocker in the prior context was "idempotency-key scope decision"—you need to agree:
- Is it per-order, per-payment-attempt, or per-subscription-cycle?
- Do you scope the constraint to a time window (365 days) or keep it forever?
- Who generates the key—API caller or your system?

**Next step**: Clarify scope with your team (likely 15 min), then implement idempotency keys in the Stripe handler + DB constraint. That's the device that prevents this class of error entirely.

What's blocking the scope decision?