I'll analyze this through the poka-yoke hierarchy to see if your fix is sufficient.

**Current Fix Analysis**

Your amount-matching check is **detection-level** mistake-proofing — it catches duplicates after they've already been attempted. This has critical weaknesses:

1. **False negatives**: Same customer, different amount (subscription + one-time charge)
2. **Race conditions**: Two workers checking simultaneously before either writes
3. **Legitimate duplicates**: Customer intentionally makes same purchase twice
4. **Amount collisions**: Different customers, same amount, same time window

This happened twice already. Detection didn't prevent it — and detection-based fixes often fail under load or edge cases.

**Elimination-Level Controls** (what you actually need)

Move up the poka-yoke ladder to make duplicate charges **impossible**:

```
★ Insight ─────────────────────────────────────
1. Stripe idempotency keys guarantee the exact same request only executes once — even across retries, timeouts, and network failures
2. State machines with guarded transitions prevent impossible state combinations (can't charge if status ∈ {charging, charged})
3. Exactly-once semantics beat at-least-once + deduplication every time
─────────────────────────────────────────────────
```

**Recommended Architecture**

1. **Idempotency Keys** (Stripe native)
   - Generate stable key: `idempotency_key = hash(customer_id + invoice_id + attempt_timestamp)`
   - Stripe guarantees: same key = same result, no duplicate charge
   - Handles: timeouts, retries, queue redelivery

2. **State Machine Guards**
   - Payment status: `pending → charging → charged` 
   - Transition guard: `if status == 'charging' or status == 'charged': abort`
   - Database constraint: `CHECK (status IN ('pending', 'charging', 'charged', 'failed'))`

3. **Outbox Pattern**
   - Single transaction: write payment record + event to outbox table
   - Separate processor reads outbox, publishes to queue
   - Eliminates: dual-write problem, partial failures

**Action Items**

Before this is "enough":
1. Audit `payments.ts` for all charge paths — ensure idempotency keys on every Stripe call
2. Add state machine with guarded transitions (I can help design the discriminated union types)
3. Add database constraints that prevent invalid state combinations
4. Load test: simulate timeout + redelivery scenarios

**The Pattern**

This isn't a one-time bug — it's a **systematic weakness**. Amount-matching is a band-aid. Idempotency keys + state machines are structural controls that make the entire class of errors impossible.

Want me to audit your `payments.ts` to identify all the charge paths that need idempotency keys? Or design the state machine types with proper guards?