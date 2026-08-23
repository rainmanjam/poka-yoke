No, that's not enough. Your current check is vulnerable to a **race condition (TOCTOU)** — between checking for a recent charge and actually creating a new one, another payment attempt could arrive, and both would pass the check and charge.

Since this is the second incident, this is a systemic idempotency problem, not a one-off timing fluke. Here's what's actually needed:

**Idempotency keys** (standard for payment systems):
1. **At Stripe**: Include an idempotency key (order ID or charge attempt ID) with every charge request. Stripe treats requests with the same key as retries—it returns the original charge, never double-charges.
2. **In your DB**: Add a unique constraint on `(order_id, idempotency_key)` or equivalent. This catches duplicates even if Stripe fails to, and prevents your own code from creating multiple charge records.

**Why your current fix fails:**
```
Time 1: Worker checks for recent charge → none found ✓
Time 2: SAME WORKER INSTANCE checks for recent charge → none found ✓
Time 3: Both workers simultaneously call Stripe → both succeed ✗
```

Stripe's idempotency keys solve this because Stripe is the source of truth—it deduplicates at the server, not at the client.

**Bigger problem:** From your notes, the queue redelivery is hitting other consumers too (emails, webhooks, ledger, Stripe handler). They're probably all non-idempotent. You'll need to:
- Audit all queue consumers for idempotency
- Implement tracking (DB table: `processed_message_id`) for consumers that can't use Stripe-style keys
- Handle redeliveries gracefully (idempotent reads are fine; idempotent *writes* need the keys + constraints pattern)

**Immediate action:** Use Stripe's native idempotency keys + add the DB constraint. That's the only pattern that actually stops double-charging.

What's blocking the scope decision on idempotency keys—is it which consumers need them, or how to plumb them through your system?