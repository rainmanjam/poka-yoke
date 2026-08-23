No — checking for "a recent charge with the same amount" is **detection**, not **elimination**. You're still letting the mistake happen, just trying to catch it. And since this is the second occurrence, you have the clearest signal you'll ever get that this class of error is real.

Let me analyze this using the poka-yoke retro framework:

## The Three Things

**Defect**: 340 customers double-charged, requiring refunds  
**Mistake**: Retry logic called `charge()` a second time after the first attempt timed out  
**Hazard**: The system permits non-idempotent payment operations to be retried

## Why Your Fix Isn't Enough

Your amount-matching check has three problems:

1. **It's rung 3 (Detection)** — you're still making the charge call and hoping your check runs first. A device at the source (Control) would make the duplicate charge *impossible*.

2. **Amount-matching is insufficient** — what happens when:
   - A customer legitimately needs two $50 charges?
   - The amount changes between attempts due to promotions/discounts?
   - The timeout was on a different operation and this charge is actually new?

3. **It fixes one call site** — how many other places retry payment operations? Webhook handlers? Subscription renewals? Refund operations? Manual retry buttons?

## The Control-Level Solution

**M2 from the hazard catalog** — Non-idempotent retryable effects:

> **Device**: a **required** idempotency key parameter, backed by a unique constraint on `(entity, key)` so the second attempt is rejected by the database rather than by hope. **Control.** An optional idempotency key is rung zero wearing a costume.

The fix hierarchy:

| Device | Rung | Why |
|--------|------|-----|
| **Stripe idempotency keys (required param)** | Control | Stripe deduplicates for 24h; same key = same response, no double charge |
| **DB unique constraint on `(customer_id, idempotency_key, created_at::date)`** | Control | Database physically prevents duplicate charges even if Stripe's dedupe fails |
| Amount-matching check | Detection | Catches it after the fact, fails on legitimate duplicates |
| "Be more careful with retries" | None | Relies on humans remembering |

## What Should Happen Next

Before implementing anything, **sweep for the class**:

1. Every other caller that charges customers
2. Every queue consumer that performs payment operations
3. Refund operations, subscription renewals, invoice generation
4. Any webhook handler that triggers financial effects
5. Run the hazard detector:
   ```bash
   python3 plugins/poka-yoke/scripts/detect_hazards.py --hazards M2
   ```

Then report: *"this hazard exists at N other sites"* — that number changes the conversation about priority.

## Implementation

Stripe natively supports idempotency keys. The fix is:

```typescript
// BEFORE (hazard present)
await stripe.charges.create({
  amount: amountCents,
  customer: customerId,
  // idempotency_key is optional — THE HAZARD
});

// AFTER (Control)
await stripe.charges.create({
  amount: amountCents,
  customer: customerId,
}, {
  idempotencyKey: `charge-${orderId}-${Date.now()}`, // REQUIRED
});
```

And enforce it:
- Make idempotency key **required** in your wrapper function
- Add a DB unique constraint as defense-in-depth
- Write the regression test that proves a duplicate key returns the same charge

Want me to write up the full retro doc and sweep your codebase for other sites with this hazard?