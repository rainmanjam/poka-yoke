This is a classic idempotency hazard. Your amount-matching check is a **detection** control — it can help, but it's not enough. Let me walk through why and what would actually prevent this.

`★ Insight ─────────────────────────────────────`
The poka-yoke hierarchy ranks controls: **elimination** (make the error impossible) beats **detection** (catch it before damage) beats **mitigation** (limit damage after). Your fix is detection-level with gaps.
`─────────────────────────────────────────────────`

## Why your current fix is insufficient

**Amount matching fails when:**
- Same customer, two legitimate orders, same amount → incorrectly blocked
- "Recent" is ambiguous — 1 minute? 5 minutes? Race window still exists
- Two workers check simultaneously, both see no charge, both proceed
- Refunds + retry → original charge is there but customer should be charged again

**The root cause is still present:** your system lacks a way to say "this specific payment intent should only execute once, ever."

## What actually prevents this

**1. Stripe Idempotency Keys (elimination-level)**
```typescript
const charge = await stripe.charges.create({
  amount: order.amount,
  customer: order.customerId,
  // This key guarantees exactly-once execution
}, {
  idempotencyKey: `order-${order.id}-charge`
});
```

Stripe stores the result for 24 hours. Second attempt with same key returns the original response — no new charge.

**2. State machine with terminal states (elimination-level)**
```typescript
// Before charging
const updated = await db.query(`
  UPDATE orders 
  SET status = 'charging', charge_attempt_id = $1
  WHERE id = $2 AND status = 'pending'
  RETURNING *
`);

if (updated.rowCount === 0) {
  // Another worker already claimed this — exit
  return;
}
```

The `WHERE status = 'pending'` acts as a mutex — only one worker can transition.

**3. Outbox pattern for queue reliability**
Instead of charging directly and hoping the queue acks, write the charge intent to a transactional outbox table, then process it with idempotency.

---

## Your action items

| Priority | Action |
|----------|--------|
| **Now** | Add idempotency keys to all Stripe calls using a deterministic key (e.g., `order-{id}-{action}`) |
| **Now** | Add `WHERE status = 'pending'` guard before any payment state transition |
| **This week** | Audit all payment state transitions for missing terminal-state checks |
| **This week** | Add a pre-charge lookup: `stripe.charges.list({ customer, metadata: { order_id } })` as defense-in-depth |

The idempotency key is the real fix. It moves you from "detect duplicates heuristically" to "duplicates are structurally impossible."

Want me to audit your actual payment worker code and show exactly where to add these controls?