No, amount matching is **detection-level** and won't prevent this from happening again. Since this is the second occurrence, you need **elimination-level** controls.

## Why amount matching fails

Your current fix will have:

**False positives** (blocks legitimate charges):
- Subscription renewals (same amount monthly)
- Installment payments
- Multiple line items with identical totals

**False negatives** (misses duplicates):
- Race condition: both workers check simultaneously, both see "no recent charge," both proceed
- Amount variations: partial refund then retry, currency conversion differences, tax recalculation
- Time window: if "recent" is too short, misses slow retries; too long, blocks legit charges
- Different payment methods or invoice IDs for the same logical charge

## Elimination-level fixes

Since this is recurring, you need multiple layers:

### 1. **Idempotency keys** (Stripe handles deduplication)
```typescript
const idempotencyKey = `charge_${customerId}_${invoiceId}_${attempt}`
stripe.charges.create({ ... }, { idempotencyKey })
```
- Same key within 24h = Stripe returns original charge, no double-charge
- This is what idempotency keys are FOR

### 2. **State machine guards**
```typescript
// Atomic state transition
UPDATE payments 
SET status = 'charging', worker_id = $1
WHERE id = $2 AND status = 'pending'
RETURNING id

// If no rows returned → already being processed
```

### 3. **Outbox pattern**
```typescript
BEGIN;
  INSERT INTO charge_attempts (customer_id, amount, status) 
  VALUES (..., 'pending');
  
  -- Call Stripe here
  
  UPDATE charge_attempts SET status = 'completed', stripe_id = $1;
COMMIT;
```
- Queue consumers check `charge_attempts` before processing
- Timeout without commit = no second attempt

## Immediate action

Add idempotency keys **today** — it's a 5-line change and Stripe guarantees no duplicates. Then audit your code for the state machine and outbox patterns.

Should I help you implement the idempotency key pattern first, or do you want to audit the payment worker code for all the race conditions?