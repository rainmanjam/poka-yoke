No, that check is not enough. Looking for "recent charge with same amount" has several failure modes:

1. **Race condition** — both workers check simultaneously, both see no recent charge, both charge
2. **False positives** — two different customers with same amount, or same customer legitimately buying twice
3. **Time window fragility** — what counts as "recent"? Too short misses retries, too long blocks legitimate purchases

`★ Insight ─────────────────────────────────────`
This is an **idempotency** problem, not a deduplication problem. The fix should make retries *safe by design*, not try to detect them after the fact.
`─────────────────────────────────────────────────`

**The robust fix: Stripe idempotency keys**

Stripe natively supports idempotency — if you pass the same key twice within 24h, they return the original response without charging again.

```typescript
// Generate a deterministic key BEFORE the first attempt
const idempotencyKey = `order_${orderId}_charge_${attemptId}`;

await stripe.charges.create(
  { amount, currency, customer },
  { idempotencyKey }
);
```

**Defense in depth:**

| Layer | Control |
|-------|---------|
| **Application** | Generate idempotency key from order ID before queuing |
| **Queue** | Use FIFO queue with deduplication (SQS FIFO, etc.) |
| **Database** | Unique constraint on `(order_id, charge_attempt)` |
| **Stripe** | Pass idempotency key to all mutating calls |

The key insight: the idempotency key must be generated *before* the message enters the queue, derived from the business entity (order ID), not the worker attempt.

Want me to review your current payment flow and sketch the idempotency-key implementation? I'd need to see the worker code and how messages are queued.