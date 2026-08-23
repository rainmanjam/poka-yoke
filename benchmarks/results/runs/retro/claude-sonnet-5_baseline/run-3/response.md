Short answer: no — the fix you shipped closes almost none of the actual hole, because it doesn't touch the case that caused the incident. Walking through why, per the retro framework:

**Defect / Mistake / Hazard**
- **Defect**: 340 customers double-charged overnight, refunded after the fact.
- **Mistake**: the queue redelivered the payment message after a Stripe timeout, and the redelivered attempt charged again.
- **Hazard**: nothing in the system ties a charge attempt to a single, once-only Stripe charge. `chargeCustomer` (and Stripe's own API) support idempotency keys, but nothing requires one — retries are "safe" only by convention, not by construction.

**Why the "check for a recent charge" fix doesn't close it**
It's a check-then-act (TOCTOU) guard against your *own* DB, and it fails on exactly the path that fired last night:
1. Attempt 1 calls Stripe, Stripe accepts the charge, but the response is slow — your worker times out *before* it writes the "charge succeeded" row.
2. The queue redelivers. Attempt 2 checks for "a recent charge with this amount" — finds nothing, because attempt 1 never got far enough to record it — and charges again.

The timeout-then-redeliver race is the one scenario this check cannot see, and it's the one that actually happened. It also has a second problem independent of timing: matching on amount alone will false-block two legitimate same-amount purchases from one customer close together, and won't reliably catch a duplicate if the amount differs by a cent (rounding, partial refund adjustment, etc.).

**Why nothing caught it the first time either**: no reconciliation against Stripe's own charge ledger, and no idempotency key sent to Stripe itself — so even Stripe couldn't dedup it on your behalf, which is exactly what that field is for.

**Class sweep** — same hazard, not just this one call site (checked `benchmarks/fixtures/payments.ts`, which mirrors this worker's shape):
- `chargeCustomer()` — no idempotency key parameter at all.
- its own internal `retry=true` branch recurses into itself with no key either — a second instance of the same hazard *inside the same function*.
- `handleWebhook()` on `invoice.paid` calls `chargeCustomer` directly — Stripe redelivers webhooks too, so this is a second live path to the same double-charge, independent of your queue.
- `transfer()` (balance move between accounts) has the same "no idempotency/atomicity guard on a money-moving op" shape, different failure mode (lost update under concurrency) — flagging, not folding into this fix.

**Devices** (this is the second occurrence — push for Control, not another check):

| Device | Rung | Covers | Status |
|---|---|---|---|
| Make `idempotencyKey` a required param on `chargeCustomer`, passed to `stripe.charges.create({ idempotencyKey })` | Control | the function itself, its internal retry branch, and forces every future caller to supply one | proposed |
| Unique DB constraint on `charges(invoice_id)` (or `customer_id, idempotency_key`) | Control | any caller, including ones not yet written | proposed |
| Track processed Stripe `event.id`s in the webhook handler before charging | Control | webhook redelivery specifically — a second live trigger you haven't hit yet | proposed |
| Regression test: fire the same webhook/charge call twice, assert exactly one Stripe charge + one DB row | Detection | proves the fix; catches regressions on this path | to write |
| Nightly reconciliation vs. Stripe's charge list | Detection | anything that still slips through | proposed |

**Recommendation**: replace the amount-match check with a required idempotency key threaded through to Stripe (deterministic, e.g. derived from invoice ID), plus the DB unique constraint. That's the version that survives the timeout case, because Stripe itself returns the original charge object on a duplicate key instead of creating a new one — you're not trusting a timing-dependent read anymore.

Want me to write the actual `docs/poka-yoke/retro-2026-08-22-double-charge.md` and implement the idempotency-key change against `chargeCustomer`/`handleWebhook` in `benchmarks/fixtures/payments.ts`?