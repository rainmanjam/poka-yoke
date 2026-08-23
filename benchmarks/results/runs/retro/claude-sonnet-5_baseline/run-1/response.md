**Short answer: no, the same-amount check is not enough — it treats a race condition with a probabilistic guess instead of closing it.**

Applying the retro framework:

**Defect**: 340 customers charged twice; all refunded.
**Mistake**: the worker called `charge()` a second time when the queue redelivered the message after the Stripe timeout.
**Hazard**: the charge path has no built-in guarantee that "one order → one charge," even though the queue is at-least-once (so redelivery is *expected*, not exceptional). Nothing at the API-call or database layer makes a duplicate impossible — only a downstream check tries to notice it after the fact.

**Why it was possible, run to a constraint, not a person:**
Double charge → worker retried on redelivery → retry didn't recognize it was the same logical operation → the charge request carries no key tying it to the original order/message → why not? → Stripe's request-level idempotency key isn't being used, and there's no DB constraint that a given order can have at most one successful charge → why wasn't that added? → the mitigation after the first incident was a runtime lookup, not a constraint.

**Why the proposed fix doesn't close it:**

1. **TOCTOU race.** "Check for a recent charge, then charge" is two steps, not one. If the timeout was short and the queue redelivers fast, or if two workers pick up the redelivered message concurrently, both can pass the check before either has recorded a charge. This is exactly the shape of bug that caused the incident — a check that runs before the effect it's checking for is guaranteed to exist.
2. **The lookup can legitimately come back empty on the exact failure mode that caused this.** The worker timed out *waiting on Stripe* — meaning Stripe may have already processed the first charge, but your own "recent charges" table might not be written yet (if it's populated from Stripe's response, and that response is what got lost to the timeout). The check queries a table that doesn't yet reflect the pending charge it's trying to catch.
3. **"Same amount" is a weak proxy for "same operation."** A customer legitimately charged twice for the same amount in a short window (two subscriptions, a purchase + a top-up) gets silently blocked — a new failure mode traded for the old one. It's matching on a coincidental attribute, not an identity.
4. **It's a rung-3 (Detection) device wearing a rung-1 (Control) costume.** It reduces the odds of a repeat but doesn't make the duplicate structurally impossible, which is what you want for money after a second incident.

**The Control-rung fix:**

- **Use Stripe's idempotency key correctly**: derive it deterministically from something stable per logical charge attempt — the order ID or an internal `payment_intent_id`, not a random UUID generated per call. Every retry (worker retry, queue redelivery, manual replay) sends the *same* key, so Stripe returns the original charge object instead of creating a new one. This is the mechanism designed for exactly this failure — a timeout mid-request where you don't know if it succeeded.
- **Back it with a DB unique constraint**, not just an app-level check: `UNIQUE(order_id)` or `UNIQUE(idempotency_key)` on your own charges/payments table, written in the same transaction as marking the order as "charge in flight." A second worker hitting that constraint gets a DB-level rejection, which can't race the way a `SELECT` then `INSERT` can.
- Keep a regression test that simulates "Stripe accepted but response was lost to timeout, message redelivered" and asserts exactly one charge — that's the detection layer, valuable but not sufficient alone.

**Class sweep — worth doing before you close this:** any other consumer on this same queue that makes an external side-effecting call (refunds, inventory decrements, notification/webhook sends) has the identical hazard if it isn't keyed off a stable idempotency identifier. Since this is the second occurrence, it's also worth checking whether the *first* incident's fix was similarly a lookup/checklist item rather than a constraint — that pattern (rung-3 fix after rung-1 was needed) is itself worth naming as the thing to stop doing.

If you point me at the actual worker code (this repo doesn't contain your production payment service — it's the poka-yoke skill/benchmark repo), I can write the idempotency-key change and the migration for the unique constraint directly, and a test that reproduces the timeout-redelivery race before/after.