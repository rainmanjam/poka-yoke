Now I can give you a proper analysis. Your fix is not enough — it's a heuristic that can fail in both directions. Here's the retro:

---

## Retro — Double-charge from queue retry — 2026-08-20

**Defect**: 340 customers charged twice  
**Mistake**: The retry path called charge again after the first attempt timed out  
**Hazard**: The charge operation has no idempotency enforcement — duplicates are possible and silent

### Why it was possible

```
Double charge
  ← retry called charge() twice
    ← worker timed out but Stripe succeeded
      ← queue redelivered (at-least-once, as designed)
        ← no idempotency key passed to Stripe
          ← idempotency key is optional or absent in the charge function
            ← no database constraint prevents duplicate charges for the same intent
```

**Root hazard**: The system permits charging without an idempotency key, and nothing at the database or Stripe level rejects the duplicate.

### Why your fix is insufficient

Your fix — "check for a recent charge with the same amount" — is a **heuristic** that can fail both ways:

| Failure mode | What happens |
|---|---|
| **False negative** | Retry happens outside the "recent" window (clock skew, delayed redelivery) → double charge anyway |
| **False positive** | Legitimate same-amount purchase within the window → blocked incorrectly |
| **Race condition** | Two workers check simultaneously before either writes → both charge |

This is **rung 2 at best** (warning) — and a weak one. It relies on heuristics and timing rather than identity. The hazard catalog calls this out directly:

> **An optional idempotency key is rung zero wearing a costume.**

### The correct device (Control rung)

**1. Required idempotency key in the charge function**
```typescript
// BEFORE — hazard: optional key
function charge(customerId: string, amount: number, idempotencyKey?: string)

// AFTER — control: required key
function charge(customerId: CustomerId, amount: Money, idempotencyKey: IdempotencyKey)
```

**2. Database unique constraint**
```sql
ALTER TABLE charges ADD CONSTRAINT uq_charge_idempotency 
  UNIQUE (customer_id, idempotency_key);
```

**3. Pass the key to Stripe** — Stripe has native idempotency support:
```typescript
await stripe.charges.create(
  { amount, customer },
  { idempotencyKey }  // Stripe rejects duplicates server-side
);
```

**4. Generate the key at job creation, not execution**
```typescript
// When enqueueing
queue.send({ customerId, amount, idempotencyKey: `charge-${orderId}` });

// Worker uses the key from the message — retries get the same key
```

### Why this is Control, not Warning

| Layer | What it stops |
|---|---|
| Required parameter | Caller cannot forget — won't compile/lint without it |
| Database constraint | Second insert fails even if code has a bug |
| Stripe idempotency | Second call returns the original charge, not a new one |

The mistake becomes **impossible**, not just detectable.

---

`★ Insight ─────────────────────────────────────`
**This is the second time** — that's the clearest signal you have a rung-0 fix masquerading as a control. Time-based + amount-based matching is exactly the kind of "almost works" heuristic that survives code review but fails under real queue behavior. The fact that it happened again means the previous fix also left the hazard open.
`─────────────────────────────────────────────────`

### Recommended actions

1. **Audit every queue consumer** — anywhere a retry can reach a charge, email, webhook, or external mutation needs an idempotency key
2. **Make the parameter required** — the signature change forces every caller to supply one
3. **Add the database constraint** — defense in depth, catches bugs in new code
4. **Use Stripe's idempotency** — they already built the server-side protection

Would you like me to audit your payment worker code for the specific implementation, or sweep your codebase for other non-idempotent retry paths?