No — the amount-match check is a patch on the symptom, not a fix for the hazard, and the fact that this is the second time confirms it.

**Separating the three things:**
- **Defect:** 340 customers double-charged.
- **Mistake:** the redelivered message called the charge function a second time.
- **Hazard:** the charge call has no idempotency key, so Stripe (and your own system) has no way to recognize "this is the same charge, not a new one." This repo's own fixture shows the exact shape: `benchmarks/fixtures/payments.ts:37-61` — `chargeCustomer()` calls `stripe.charges.create({...})` with no `idempotencyKey`, and its own retry branch (line 56-57) re-invokes itself with nothing to dedupe against either.

**Why the new check isn't enough:**
1. **TOCTOU race.** "Look for a recent charge with the same amount, then charge" is two steps with a gap between them. If the queue redelivers before the first charge's write is visible to the check (which is exactly the failure mode that just happened — fast redelivery under load), both attempts see "no recent charge" and both charge. You've built the same race you're trying to close.
2. **False positives with a real cost.** A customer legitimately charged $50 twice in a short window (two separate purchases) now silently has their second charge dropped. That's a new, quieter defect — dropped revenue and a confused customer — replacing a loud one.
3. **It's a heuristic, not a constraint.** Matching on amount is a guess about what "duplicate" means. It lives in application code that can be skipped, raced, or forgotten at the next call site. Nothing forces it to run.

That puts it at Detection-rung at best, and it doesn't reliably detect. The device that actually closes this is at Control-rung: **make a charge require an idempotency key, derived deterministically from the source event** (order/invoice ID, not random), passed straight to Stripe's own `idempotencyKey` param — that's what it exists for. Back it with a DB-level unique constraint (`customer_id + idempotency_key` or `order_id` on your own charges table) so even a bug in key generation can't produce two rows. Drop the amount-match check once that's in, or keep it only as a monitor, not a gate.

**Sweep for the class** — don't stop at this one function. The same hazard (non-idempotent handler behind a redelivering queue) is available anywhere a consumer has side effects and no dedupe key:
- Every other queue consumer with side effects (emails, webhooks, ledger writes) — redelivery isn't unique to payments.
- Stripe's *own* webhook delivery also retries (`handleWebhook` in that same fixture calls `chargeCustomer` directly) — so this exact bug has two independent triggers, not one.

**On "second time":** worth checking directly — did the first incident also get a detection-rung fix (a check, a test, an alert) instead of a constraint? If so, that's the actual pattern repeating, not just double-charging specifically. Want me to draft the idempotency-key change and a retro write-up (`docs/poka-yoke/retro-2026-08-22-double-charge.md`) against your real worker code, or against the fixture here as a reference implementation first?