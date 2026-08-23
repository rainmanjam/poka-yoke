Looking at this through the poka-yoke lens: **No, that's not enough.** Amount-matching is a *detection-level* control that still allows the error to occur — you're just trying to catch it before it happens again. Here's why it's insufficient:

**Problems with amount-matching:**
1. **False negatives**: Different amounts (tax changes, promo codes, currency rounding) slip through
2. **False positives**: Legitimate same-amount charges get blocked (subscriptions, recurring donations, multiple family members)
3. **Race condition**: Two workers can both check, both see no recent charge, both proceed
4. **Window brittleness**: "Recent" is arbitrary — too short misses slow duplicates, too long blocks legitimate retries

**This is recurring because you're treating symptoms, not causes.** The root issue is **missing idempotency guarantees** in a distributed system with at-least-once delivery.

`★ Insight ─────────────────────────────────────`
**Poka-yoke ladder for payment double-charges:**
- **Elimination** (best): Stripe idempotency keys — physically impossible to charge twice with same key
- **Replacement**: Outbox pattern + state machine — charge attempt recorded in transaction BEFORE queue message
- **Facilitation**: Stripe checkout sessions — Stripe owns dedup
- **Detection** (weakest): Your amount-check — finds duplicates *after* they happen
`─────────────────────────────────────────────────`

## Elimination-level fix (recommended):

1. **Stripe idempotency keys** (stops duplicates at API level):
   ```typescript
   await stripe.charges.create({
     amount: 1000,
     currency: 'usd',
     source: token,
   }, {
     idempotencyKey: `charge_${userId}_${subscriptionId}_${billingPeriod}`
     // Retry with same key = same charge, guaranteed by Stripe
   });
   ```

2. **State machine guard** (prevents duplicate attempts):
   ```typescript
   // In transaction with charge record:
   UPDATE charges SET status = 'processing' 
   WHERE id = ? AND status = 'pending'
   RETURNING *;
   // If no rows: already processing/complete, abort
   ```

3. **Outbox pattern** (atomic state + message):
   ```typescript
   BEGIN TRANSACTION;
     INSERT INTO charges (id, status) VALUES (?, 'pending');
     INSERT INTO outbox (event_type, payload) VALUES ('charge', ?);
   COMMIT;
   // Queue reads outbox, even if worker crashes
   ```

**What to do now:**
- Add Stripe idempotency keys immediately (1 line change, eliminates 99% of risk)
- Audit payment code for other at-least-once assumptions (refunds, subscriptions, webhooks)
- Keep the amount-check as defense-in-depth monitoring/alerting, not primary control

Want me to audit the payment worker code to find other similar hazards, or help implement the idempotency key pattern?