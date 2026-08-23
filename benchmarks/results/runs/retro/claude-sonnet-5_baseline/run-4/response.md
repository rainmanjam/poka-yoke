**Short answer: no, that guard is not enough.** It changes the shape of the bug, it doesn't close the hazard — and the fact that this is the second time is itself diagnostic.

**Defect:** 340 customers charged twice overnight; refunded.
**Mistake:** on Stripe timeout, the queue redelivered the message and the worker called charge again.
**Hazard:** the charge path has no enforced idempotency — nothing (API contract, DB constraint, or type) makes it *impossible* to submit the same logical charge twice. "Check for a recent charge of the same amount" is a heuristic bolted in front of that hazard, not a fix to it.

Why the guard doesn't hold:

1. **TOCTOU race.** Redelivery under a timeout is exactly the condition that produces two workers (or two rapid attempts) racing: both read "no recent matching charge," both proceed, both charge. The check and the charge aren't atomic, so the guard is weakest precisely when the failure mode is most likely to fire.
2. **Wrong key.** "Same amount" is neither necessary nor sufficient — two legitimate $19.99 orders from the same customer close together get falsely blocked; a duplicate whose amount shifts (proration, rounding, currency) sails through.
3. **Solving it at the wrong layer.** Stripe already gives you exactly this primitive — an `Idempotency-Key` header keyed on something stable like your order ID. Not using it means you're re-implementing (worse) something the payment processor already guarantees at the API layer.
4. **Rung.** This is a Detection-rung device — a lookup before acting. It can miss, and under the exact conditions that caused the incident, it's likely to.

**Why this is the second time:** if the first incident's fix was also a check/detection-style patch rather than a structural constraint, that's the pattern — fixes are landing at the mistake level (this call site) instead of the hazard level (the queue delivers at-least-once and downstream side effects aren't idempotent). The hazard survives and resurfaces wherever else the same queue drives a non-idempotent action.

**Devices, by rung:**
- **Control:** pass a stable `Idempotency-Key` (order/invoice ID, not a timestamp) on every Stripe charge call.
- **Control:** unique DB constraint on `(order_id)` or `(idempotency_key)` in your own charges table, written transactionally with/before the Stripe call — so even a bug in the Stripe path can't produce two committed charge rows for one order.
- **Detection (keep, don't rely on):** a reconciliation job flagging >1 charge per order_id — a safety net, not the defense.

**Class sweep (do before closing this out):** any other consumer on that same at-least-once queue with a non-idempotent side effect — refund issuance, customer emails/webhooks, ledger postings, inventory decrements. Same redelivery hazard, same missing constraint, until each is checked.

If you want, I can write this up as `docs/poka-yoke/retro-2026-08-22-double-charge.md` per the skill's template — but I'd need the actual worker/queue code (this repo doesn't contain a payment worker, so point me at the right repo/paths) to do the class sweep for real rather than in the abstract.