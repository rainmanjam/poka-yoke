No, that's **not enough** — and the fact that this is the second time proves it. Let me walk through this using the poka-yoke framework.

## Separating the three things

**Defect**: 340 customers were double-charged  
**Mistake**: The retry path called charge again without deduplication  
**Hazard**: The charging system accepts duplicate payment attempts and has no built-in idempotency guarantee

Your fix — checking for "a recent charge with the same amount" — is **detection at best**, and weak detection at that:
- **False negatives**: Two legitimate $50 charges within the window look like a duplicate
- **Missed duplicates**: Same customer, different amounts (e.g., $49.99 vs $50.01 due to tax calculation)
- **Timing window**: "Recent" is arbitrary — what if the worker is delayed?
- **Still post-hoc**: You're detecting the duplicate *after* you've decided to charge, not preventing the second charge from being *possible*

## Why this keeps happening

The root cause isn't "the worker timed out" — timeouts are a constant in distributed systems. The root cause is:

> **Your payment system allows the same logical charge operation to execute multiple times without idempotency protection.**

This is a **Control-rung** problem that you're solving at the **Detection rung**. And since it's happened twice, you have strong evidence that detection isn't working.

## What Control-rung fixes look like

These make the duplicate charge **impossible**, not merely caught:

### 1. **Stripe idempotency keys** (ELIMINATION)
```typescript
// Before (hazardous)
await stripe.charges.create({
  amount: 5000,
  customer: customerId
  // No idempotency key → same request can charge twice
})

// After (Control-rung)
await stripe.charges.create({
  amount: 5000,
  customer: customerId
}, {
  idempotencyKey: `charge_${invoiceId}_${attempt}`  // REQUIRED, not optional
})
```

Stripe guarantees: same key = same result, no duplicate charge, even if called 1000 times.

### 2. **State machine guards** (MOTION-STEP)
```typescript
// Charge can only happen from specific states
type PaymentState = 
  | { status: 'pending' }
  | { status: 'processing', chargeId: string }
  | { status: 'succeeded', chargeId: string, paidAt: Date }
  | { status: 'failed', reason: string }

// Attempting to charge from 'processing' or 'succeeded' is a type error
```

### 3. **Database unique constraint** (CONTROL)
```sql
CREATE UNIQUE INDEX idx_one_successful_charge_per_invoice 
ON charges(invoice_id) 
WHERE status = 'succeeded';

-- Second INSERT for same invoice fails at DB level
```

### 4. **Outbox pattern** (MOTION-STEP)
```typescript
// Write to outbox in same transaction as charge intent
// Outbox processor ensures exactly-once delivery
// Queue redelivery hits idempotent outbox processor, not charge endpoint
```

## Questions to ask yourself

1. **How many other payment endpoints have this same hazard?** (Subscription charges? Refunds? Payouts?)
2. **Do your queue workers use idempotency keys for *any* Stripe operations?**
3. **What happens if the charge succeeds but writing the result to your DB times out?** (You might retry and charge again)
4. **What happens if two workers dequeue the same message?** (Rare but possible in some queue systems)

Run the hazard detector to find similar patterns:
```bash
python3 plugins/poka-yoke/scripts/detect_hazards.py \
  --paths src/payments \
  --category dangerous-defaults
```

## What to do

Since this is **recurrence #2**, you need Control-rung fixes:

1. **Immediate**: Add Stripe idempotency keys to *all* charge operations (not optional parameter — required)
2. **Short-term**: Add database constraint preventing duplicate successful charges per invoice
3. **Regression test**: Prove the fix (simulate timeout → retry, verify single charge)
4. **Sweep**: Audit every Stripe API call for missing idempotency keys
5. **Document**: Write to `docs/poka-yoke/retro-2026-08-20-double-charge.md` following the template in the skill

Your amount-matching check can stay as **defense in depth**, but it's not the primary device — it's a Warning-rung alert that fires if the Control-rung devices somehow fail.

★ **Insight** ─────────────────────────────────────  
The difference between Detection and Control: Detection says "we'll catch it if it happens again." Control says "it cannot happen again." After 680 customers affected (340 × 2 incidents), you need Control. The amount-match check is better than nothing, but Stripe idempotency keys are *designed exactly for this failure mode* — use them.  
─────────────────────────────────────────────────────

Want me to help you audit the payment code for all the places this hazard exists?