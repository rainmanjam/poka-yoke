No — that check closes the hole you already found, but it's not the same class of fix, and "second time" is the tell.

**The three things, separated:**
- **Defect:** 340 customers charged twice overnight.
- **Mistake:** the queue redelivered a message after a Stripe timeout, and the retry called `charge()` again.
- **Hazard:** `charge()` has no idempotency guarantee. Nothing about the system — not Stripe, not your DB, not the queue consumer — refuses to record two successful charges for the same logical intent. The queue's at-least-once redelivery is not the bug; it's doing its job. The bug is that your consumer isn't idempotent, which is a precondition for consuming an at-least-once queue at all.

**Why the new check isn't enough:**
"Look for a recent charge with the same amount before charging" is check-then-act, not a constraint — it's the same shape of race that caused the original incident, one level up:

1. **TOCTOU race.** Two redeliveries (or two worker replicas) can both run the "any recent charge with this amount?" query, both see nothing, both proceed. This isn't hypothetical — the thing that caused this incident (a slow Stripe call under load) is exactly the condition that makes concurrent redeliveries likely.
2. **Weak key.** "Same amount" is neither necessary nor sufficient: a customer legitimately buying the same $9.99 item twice in a short window gets wrongly blocked; a charge whose amount shifts slightly (tax, proration, currency rounding) on retry sails through as a "different" charge.
3. **It's a rung-3 device (Detection), not rung-1 (Control).** It fires after the fact, on the one path someone thought to guard. It's a reasonable stopgap for last night, but it's the kind of fix that produces a third incident with a slightly different timing window.

**What Control-rung actually looks like here:**
- Generate a deterministic idempotency key per logical charge (e.g. `order_id`, not a random UUID per attempt) and pass it as Stripe's `idempotency_key`. Stripe then guarantees exactly-once processing server-side — including under the exact timeout-then-retry sequence that caused this.
- Add a unique constraint in your own ledger on `order_id` (or `(order_id, idempotency_key)`) for successful charges. Then even a bug that calls `charge()` from two different code paths for the same order fails on insert instead of racing on a `SELECT`.

Do both — Stripe-side prevents the double charge at the processor, the DB constraint prevents double-recording for any other route that reaches `charge()`.

**On "second time":** before calling this closed, sweep for the same hazard elsewhere — any other queue consumer in this system that isn't idempotent (order confirmation emails, webhooks, ledger writes, inventory decrements) has the identical failure mode waiting for its own timeout. Worth telling me if you want that swept now, or if you'd like this written up as `docs/poka-yoke/retro-2026-08-22-double-charge.md` per the repo's convention.