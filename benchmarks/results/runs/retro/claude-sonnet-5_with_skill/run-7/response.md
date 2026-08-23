Confirmed — there's no actual payment worker code in this repo (this is the poka-yoke skill's own project; the double-charge scenario is literally the worked example in `retro/SKILL.md`). So this is a consultation, not a file to edit. Applying the retro method:

**No, the fix isn't enough — it's rung 2 at best, and it's leaky even there.**

**Separating the three things:**
- **Defect**: 340 customers double-charged.
- **Mistake**: the retry (queue redelivery after the Stripe timeout) called the charge path again with no way to recognize it as the same logical payment.
- **Hazard**: nothing in the system — not Stripe, not your DB — enforces that one logical charge can only ever produce one real charge. The charge call is not idempotent.

**Why the "recent charge, same amount" check doesn't close that hazard:**
1. **It's check-then-act, not atomic.** Two workers processing near-simultaneously (which is exactly what queue redelivery does — the original attempt and the redelivered one can be in flight together) can both query "any recent charge this amount?", both see nothing, both proceed. This is the same race that caused the incident, just with a guard clause in front of it that doesn't hold under concurrency. Rung 2 (warning) requires the check to *always* fire before the action; a racy check doesn't reliably do even that.
2. **It matches the wrong thing.** Amount isn't a logical-operation identifier. Two genuinely separate charges to the same customer for the same amount (common — subscriptions, repeat purchases) will get incorrectly suppressed. You'd trade one incident class for a quieter one.
3. **It lives in application code with no backing constraint.** If anyone adds a second worker instance, a new code path, or a retry helper that doesn't go through this exact check, the hazard is back with zero warning.

**The control-rung fix**, per the ladder: two redundant devices, not one heuristic —
- **Stripe-side**: pass a deterministic idempotency key on every charge request, derived from the *order/payment-attempt ID* (not amount) — Stripe will refuse to double-execute a request with a key it's already seen, even under concurrent redelivery.
- **DB-side**: a unique constraint on `(order_id)` or `(idempotency_key)` in your own charges table, so even if the Stripe call path is ever bypassed or misused, a second insert for the same order fails at the database, not silently succeeds.

That's belt-and-suspenders at rung 1 — the mistake becomes structurally impossible, not just less likely.

**Sweep for the class (this is the step that matters given "second time"):** the underlying hazard is "a queue consumer isn't idempotent under at-least-once redelivery" — that pattern is very unlikely to be unique to the payment worker. Worth checking every other queue consumer for the same shape: emails/notifications, webhook dispatch, ledger writes, inventory decrements, anything that mutates external or persistent state on message handling.

**Verify before closing it**: redeliver the same message twice in a test and confirm the second attempt is rejected (both at Stripe and at the DB constraint), not just "doesn't seem to double-charge in practice."

Want me to write this up as a `docs/poka-yoke/retro-2026-08-22-double-charge.md` per the skill's format, and/or do the sweep across your actual payment-worker repo (if you point me at it — this repo doesn't contain that code)?