That fix has a race condition and isn't precise enough. Two workers could check simultaneously before either writes, or two legitimate $49.99 charges for different orders would block each other.

This is a textbook idempotency problem — Stripe has a built-in solution for exactly this.

`★ Insight ─────────────────────────────────────`
**Why "same amount recently" fails:**
1. **Race window**: Check-then-charge isn't atomic — parallel workers can both pass the check
2. **False positives**: Legitimate same-amount charges get blocked
3. **False negatives**: Different amounts for same order slip through

**The poka-yoke solution — make double-charge impossible:**
Stripe idempotency keys. Pass a deterministic key derived from your internal order/payment ID. Stripe guarantees: same key within 24h → same result, no duplicate charge.
`─────────────────────────────────────────────────`

Here's the pattern:

```python
# Derive key from YOUR stable identifier, not Stripe's
idempotency_key = f"charge_{order_id}_{payment_attempt_id}"

stripe.Charge.create(
    amount=amount,
    currency="usd",
    customer=customer_id,
    idempotency_key=idempotency_key,  # Stripe dedupes on this
)
```

**Why this works:** The key is computed *before* calling Stripe, so retries send the exact same key. Stripe's servers handle the deduplication atomically — no race window.

**Additional hardening:**
- Store payment state (`pending → charging → charged`) and only process `pending` rows
- Use a transactional outbox: commit state change and enqueue in same transaction
- Set your queue's visibility timeout > Stripe's typical response time

Want me to audit your payment worker code to identify where to add the idempotency key and state transitions?