Let me analyze this properly using the retro framework.

---

## The Three Things

| | |
|---|---|
| **Defect** | 340 customers double-charged overnight |
| **Mistake** | Retry path called charge again without an idempotency key |
| **Hazard** | The payment system has no mechanism that makes duplicate charges for the same logical intent impossible |

Your proposed fix — "check for a recent charge with the same amount" — is **Rung 3 (Detection) at best**, and has serious holes:

| Problem | Why it fails |
|---|---|
| "Same amount" is not a unique key | Two different customers paying $49.99 would collide |
| "Recent" is undefined | If the queue backs up for 10 minutes, is that recent? |
| Race condition | Two workers can both pass the check before either writes |
| It's a check, not a constraint | Nothing stops a future code path from skipping it |

This is not enough. You already have proof it isn't — **this is the second time**.

---

## The Device You Need: Idempotency Key (Rung 1 — Control)

```
★ Insight ─────────────────────────────────────
Shingo's rule: if a mistake has happened twice, the system is
telling you exactly where to install a device. The evidence
doesn't get stronger than "this already hurt real users."
─────────────────────────────────────────────────
```

The correct device is a **required idempotency key** with a **database unique constraint**:

1. **The key**: Generate a deterministic key at the *source* of the payment intent — typically `{queue_message_id}` or `{order_id}:{attempt_purpose}`. Not at the worker.

2. **Required parameter**: `charge(customerId, amount, idempotencyKey)` — no optional, no default. If it compiles without a key, it can ship without a key.

3. **Database constraint**: `UNIQUE (customer_id, idempotency_key)` on your charges table. Not a check-then-insert — a constraint that the database enforces atomically.

4. **Stripe already supports this**: Pass `Idempotency-Key` header to Stripe's API. They dedupe for 24 hours and return the original response on replay.

---

## Why Your Fix Keeps Failing

Your current approach is a **check-before-write** pattern:

```
if (recent_charge_with_same_amount_exists) return;
charge();  // ← race window here
```

The race window between checking and writing is exactly where duplicates slip through. A unique constraint eliminates the window:

```
try {
  insert_charge_with_idempotency_key();  // atomic
  stripe.charge({ idempotencyKey });
} catch (UniqueViolation) {
  return existing_charge;  // idempotent
}
```

---

## Class Sweep

Before closing this, check:
- Every other queue consumer that calls a payment endpoint
- Any webhook handler that triggers charges
- Subscription renewal jobs
- Retry/recovery scripts

The hazard ("optional idempotency key" or "no idempotency at all") likely exists at multiple sites.

---

## Recommended Actions

| Device | Rung | Status |
|---|---|---|
| Make idempotency key a **required** parameter to charge functions | Control | **Do this** |
| Add `UNIQUE(customer_id, idempotency_key)` constraint on charges table | Control | **Do this** |
| Pass `Idempotency-Key` to Stripe on every charge | Control | **Do this** |
| Remove the "same amount" check | — | It gives false confidence |
| Add regression test that attempts double-charge with same key | Detection | Proves the device |

Want me to look at the actual payment worker code to show what the implementation should look like?