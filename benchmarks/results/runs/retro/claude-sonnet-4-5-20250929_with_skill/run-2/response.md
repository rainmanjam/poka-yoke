No, that's not enough — it's detection-level (rung 3), and since this is the **second time**, you need elimination. Let me work through the poka-yoke analysis.

## The three things

- **Defect**: 340 customers double-charged
- **Mistake**: Retry path called the charge function again after timeout
- **Hazard**: The payment system permits duplicate charges for the same logical transaction — no idempotency enforcement, no state machine preventing re-execution

## Why the proposed fix is fragile

Checking for "a recent charge with the same amount" fails in multiple ways:

**Contact lens** (can the wrong thing fit?):
- Two legitimate $50 charges look identical to one duplicated $50 charge
- Amount-only matching has no notion of transaction identity
- "Recent" is a time window, not a logical boundary

**Motion-step lens** (can steps happen in wrong order?):
- Nothing prevents: start charge → timeout → mark failed → retry succeeds → first charge completes
- No state tracking whether this *logical payment* has completed

This is **detection at best** — and detection that only works when amounts happen to match and timing happens to align. It's the same rung as the first fix (which also failed).

## What elimination looks like (Control — rung 1)

The fact that this recurred means you need devices that make the mistake **impossible**, not harder:

| Device | Rung | What it prevents | Implementation |
|--------|------|------------------|----------------|
| **Stripe idempotency keys** | Control | Duplicate charge submissions to Stripe — Stripe deduplicates server-side | Make `idempotency_key` a **required** parameter; generate from `(customer_id, invoice_id, attempt_timestamp)` |
| **Database unique constraint** | Control | Multiple successful charge records for same transaction | `UNIQUE(customer_id, invoice_id)` or add `idempotency_key` column with unique constraint |
| **State machine** | Control | Charging from already-charged states | Typestate or status enum: `pending → (charging | succeeded | failed)`; transition to `charging` must be atomic; cannot charge from `succeeded` |
| **Outbox pattern** | Control | At-most-once semantics violated by queue redelivery | Write intent to DB, process from outbox table with `SELECT ... FOR UPDATE SKIP LOCKED`, mark processed; queue delivers many times but DB processes once |

**The idempotency key is the standard solution** — Stripe has this built in for exactly this reason. Every charge attempt should include a key derived from the logical transaction identity, not from the retry attempt.

## Class sweep

Before implementing, find every other place the same hazard exists:

```bash
# Find all charge/payment operations
grep -r "stripe.*charge\|payment.*create\|\.charge(" 

# Find all message queue consumers that mutate financial state
grep -r "queue.*process\|consumer.*handle" | grep -i "payment\|charge\|refund\|transfer"

# Run the hazard detector
python3 /path/to/detect_hazards.py --paths . --categories idempotency,state-mutation
```

Look for:
- Other Stripe operations (refunds, transfers, payouts)
- Other queue-processed mutations (subscription changes, credit adjustments)
- Sibling functions with optional idempotency parameters
- Scripts/jobs that could run twice

## Why "this is the second time" matters

The recurrence tells you **the first fix closed the symptom, not the hazard**. The underlying system property — that duplicate charge attempts succeed silently — is still true. That's why amount-matching won't be enough either.

After two incidents, you have ironclad justification to:
1. Make idempotency **required** (break callers that don't provide it)
2. Add database constraints (migration required)
3. Spend engineering time on the state machine refactor

These are expensive at rung 0 (before anything breaks). At rung "this cost us 340×refund + support + trust", they're cheap.

## Next steps

1. **Immediate**: Add Stripe idempotency keys to the payment worker (required param)
2. **This sprint**: Class sweep — find all similar queue consumers
3. **Next sprint**: Database constraint or state machine (choose based on architecture)
4. **Regression test**: Simulate timeout + redelivery, verify charge happens exactly once

Want me to look at the actual payment code to identify the specific callsites and propose the exact device?