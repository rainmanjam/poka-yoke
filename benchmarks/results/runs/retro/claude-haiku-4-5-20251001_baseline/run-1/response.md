This is insufficient. Your duplicate-charge check is vulnerable to a **TOCTOU race** — the check and the charge aren't atomic, so concurrent requests can both pass the check before either one writes to the database.

**The right fix for Stripe is idempotency keys:**

Stripe natively supports idempotency via the `Idempotency-Key` header. Pass the same key on retries, and Stripe deduplicates server-side — if the timeout was transient and the first charge actually succeeded, the retry returns the original charge ID instead of charging again.

```javascript
const idempotencyKey = `order_${orderId}`; // stable across retries
await stripe.charges.create({
  amount,
  customer,
  idempotency_key: idempotencyKey, // Stripe handles dedup
});
```

**For your database, add a unique constraint:**

Even if the Stripe call succeeds twice (e.g., if you hit their API twice before the response arrives), your database should reject the second insert:

```sql
ALTER TABLE charges
  ADD CONSTRAINT unique_order_charge
  UNIQUE (order_id, stripe_charge_id);
```

This gives you two layers: Stripe deduplicates on their side, your DB deduplicates on yours.

**The bigger issue: this pattern should apply everywhere.**

Your notes mention this is the second incident. The queue-wide problem is that *any* consumer that can timeout and be redelivered (emails, webhooks, ledger entries, Stripe handler) needs idempotency. A single check in the payment worker won't stop this from happening elsewhere.

**What's the scope decision that's blocking you?** Is it whether idempotency keys should be order-scoped (one charge per order, ever) vs. payment-attempt-scoped (one charge per distinct attempt), or something else? That shapes how you structure the key and the constraint.