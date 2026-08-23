Now I have everything I need. Let me apply the retro framework to your incident.

---

## Retro Analysis — Double Charge via Queue Retry — 2026-08-20

**Defect**: 340 customers were double-charged overnight.

**Mistake**: The retry path called `charge()` again without deduplication.

**Hazard**: The charge operation accepts a retry without an idempotency key backed by a unique constraint. The system permits non-idempotent effects on a retryable path.

---

### Why it was possible

| Why | Answer |
|-----|--------|
| Why did customers get charged twice? | The queue redelivered the message after a Stripe timeout |
| Why did the second attempt charge again? | No idempotency key was passed to Stripe, and no unique constraint prevented a duplicate |
| Why was there no idempotency key? | **The key is optional — or absent entirely — in the charge function signature** |
| Why did nothing at the database level reject it? | **No unique constraint on `(customer_id, idempotency_key)` or `(order_id, charge_id)`** |

The terminal answer is: **the system has no control-rung device preventing duplicate charges.** The charge path accepts retries without requiring proof they're safe.

### Why nothing caught it

At-least-once delivery is the queue's contract — your queue did exactly what it's supposed to do. The escape question is: what should have stopped the *second charge from succeeding*? Answer: a unique constraint that rejects it at the database layer.

---

### Your fix — is it enough?

> "added a check in the worker that looks for a recent charge with the same amount before charging"

**No. This is rung 0 (not a poka-yoke) wearing a rung 2 costume.**

`★ Insight ─────────────────────────────────────`
Your fix is hazard **M5: Check-then-act race** on top of hazard **M2: Non-idempotent retry**. Between `SELECT` and `INSERT`, another worker can slip through. Worse, "same amount" is not identity — two legitimate $99 charges for the same customer become a false positive.
`─────────────────────────────────────────────────`

| Problem with the fix | Why |
|----------------------|-----|
| Race condition | Check runs, second worker checks, both see no charge, both charge |
| Wrong matching criteria | Amount is not identity — legitimate same-amount purchases get blocked |
| "Recent" is fuzzy | What's the window? 1 minute? 1 hour? Stripe can retry for days |
| No database enforcement | Application-layer checks bypass easily via scripts, migrations, other services |

---

### The control-rung device

**Required idempotency key + database unique constraint.**

```
1. Derive idempotency_key from something immutable: order_id, or (customer_id, cart_hash, timestamp)
2. Pass it as a REQUIRED parameter to Stripe's charge API (Stripe respects these)
3. Store it in your charges table with a UNIQUE constraint
4. On retry, the constraint rejects the second attempt — no race, no window, no application logic
```

**Rung achieved**: Control. The second charge is **impossible** — the database rejects it before Stripe is ever called.

| Device | Rung | What it prevents |
|--------|------|------------------|
| Required idempotency_key parameter | Control | Charge call without one won't compile/type-check |
| `UNIQUE(customer_id, idempotency_key)` in DB | Control | Second attempt rejected at write time |
| Stripe idempotency key | Control | Even if your DB fails, Stripe rejects the duplicate |
| Your "check for recent charge" | Detection (flawed) | Races, false positives, bypasses |

---

### Class sweep — where else is this mistake available?

Before closing, you need to answer: **what other non-idempotent effects are reachable from a retry or queue consumer?**

- Email sends from a queue?
- Webhook dispatches?
- Inventory adjustments?
- Refund processing?
- Notification pushes?

The same hazard (M2) exists anywhere at-least-once delivery meets a side effect that shouldn't repeat.

---

### Recommended actions

1. **Make idempotency key required** in the charge function signature — not optional, not defaulted
2. **Add `UNIQUE(order_id)` or `UNIQUE(customer_id, idempotency_key)`** to your charges table
3. **Pass the key to Stripe** — they will reject duplicates even if your DB check fails
4. **Remove the "same amount" check** — it's the wrong invariant and will cause false positives
5. **Sweep for M2** across all queue consumers and retry paths

Would you like me to audit your payment worker code to identify the exact changes needed, or sweep the codebase for other M2 hazards?