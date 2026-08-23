Your current fix is **rung 2 (warning)** — it detects the mistake after someone makes it. For an incident that cost real money and recurred, you need **rung 1 (control)** — making the mistake physically impossible. Here's why the current approach fails:

## The three things

**Defect**: 340 customers charged twice, ~$[X] loss, same incident recurred.

**Mistake**: The payment worker's retry path called the Stripe `charge()` function again without passing an idempotency key.

**Hazard**: `charge()` accepts an optional idempotency key and succeeds without one. This makes duplicate charges possible at every call site, not just this worker.

## Why it was possible

- Payment worker → Stripe times out → queue redelivers → retry calls `charge()` → no idempotency key parameter → **idempotency is optional, not required**
- Why optional? Likely added after initial implementation; made optional to avoid breaking existing callers.
- Result: **the system permits charges without idempotent guarantees**

**Why nothing caught it**: No compile-time requirement, no database constraint, no test covering redelivery + timeout → charge path. The fix after the first incident was rung 0 (training) — a code review reminder that did not stick.

## Class sweep — this is critical

Your current fix only covers *one code path* and only *when the amount exactly matches*. The same hazard exists:
- Every other service calling `charge()` (emails, webhooks, ledger updates, other Stripe handlers, reconciliation jobs)
- Every non-idempotent consumer in that queue (same root cause, different resource)
- Scripts, migrations, or backfills that call `charge()` directly
- Any future code path that does not know to pass the key

**This is not one bug. It is a system design that permits a class of bugs.**

## Devices

| Device | Rung | Covers | Why it works |
|---|---|---|---|
| **Idempotency keys required** (order ID) + unique DB constraint on `(order_id, idempotency_key)` | **Control** | All charge sites, all queue consumers | Physically prevents duplicate charges; Stripe sees the same key twice and returns cached result |
| **Regression test**: Queue timeout → redelivery → charge path, verify only one charge created | **Detection** | Original path only | Proves the fix, stops this exact regression |
| Narrow amount-based check (your current fix) | Warning | One code path | Already deployed; keep it temporarily, but replace it |

---

**What you need to do:**

1. **Make idempotency keys required** in the `charge()` signature (or add a newtype wrapper that requires them). Break the call sites — that break surface is where you'll find every place charges happen.

2. **Add a unique DB constraint** on `(order_id, idempotency_key)` so the database itself rejects duplicates, even if code doesn't pass the key correctly.

3. **Audit all queue consumers** — emails, webhooks, ledger, Stripe handler, etc. The timeout + redelivery hazard exists for any of them. Apply idempotency keys to every one (idempotency key = message ID, usually).

4. **Write and verify the regression test** — reproduce the timeout scenario, confirm only one charge occurs, then ship it.

5. **Remove the amount-based check** once the constraint is live (it's a crutch and masks the real fix).

The reason this happened twice is that the first fix was rung 0: "remember to pass the key." That breaks under pressure. A constraint cannot be forgotten.