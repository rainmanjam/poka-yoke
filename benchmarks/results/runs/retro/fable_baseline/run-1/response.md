No — and the reason it's the second time is that both fixes have been at the wrong level. Here's the retro framing, then the concrete answer.

## Separate the three things

- **Defect:** 340 customers charged twice.
- **Mistake:** the redelivered message called `charge()` again.
- **Hazard:** *the charge operation can be executed twice for the same intent, and nothing in the system refuses the second one.* Stripe's timeout didn't cause this; it just exposed it. Any redelivery, retry, double-click, or replay exposes it too.

## Why the "recent charge with same amount" check isn't enough

It's a **Detection**-rung heuristic, not a Control. Specifically:

1. **It's a race.** Two workers pick up the redelivered message (or the original and the redelivery overlap — which is exactly what happens when the first worker is hung on Stripe's timeout). Both read "no recent charge," both charge. The check-then-act window is the bug itself, relocated.
2. **It checks the wrong key.** "Same amount, recently" is a guess about identity. It produces false positives (customer legitimately buys two $20 items in a row → second one silently refused) and false negatives (partial retry with a different amount, different currency rounding, a charge that timed out *before* your DB row was written so there's no "recent charge" to find).
3. **Its data source is your DB, not Stripe.** The failure mode was "Stripe succeeded but we timed out before recording it." In that state your DB says no charge exists. The check reads that and charges again. **Your fix does not cover the incident that motivated it.**
4. **It relies on memory.** Next payment path someone writes (subscription renewal, manual admin charge, retry script) won't have it.

## What Control looks like

**1. Stripe idempotency keys, derived from the intent — not generated per attempt.**
`Idempotency-Key: charge:{order_id}` (or the payment-intent/message ID). Stripe returns the original result for replays for 24h. This is the device that covers *exactly* "timed out, retried" — Stripe does the dedup, so your DB being behind doesn't matter. Make the key a **required** parameter of your charge wrapper so no caller can omit it.

**2. A database unique constraint on the intent.**
`UNIQUE (order_id)` on a `payment_attempts` table, inserted *before* calling Stripe, in its own transaction. Second worker's insert fails → it reads the existing row and reconciles instead of charging. This kills the race the heuristic can't.

**3. Use Stripe's own object as the intent.**
Create a `PaymentIntent` once (idempotently), store its ID, and have retries *confirm/retrieve* that intent rather than create charges. Then "retry" is structurally incapable of creating a second charge.

**4. Reconciliation job** (Detection, but worth having): daily diff of Stripe charges vs. your ledger. This is what tells you in 1 hour instead of "next morning, via support tickets."

## The sweep — the step that actually prevents the third incident

Before closing this: grep every place that calls Stripe (or any non-idempotent side effect — emails, refunds, inventory decrements, webhooks you emit) from a queue consumer. Each one has the same hazard. Given this is the second time, I'd bet the first incident was a different call site of the same shape, and the fix then was also local.

## What I'd do right now

1. Make idempotency key a required argument on your charge wrapper (one-line signature change; compiler/linter finds every caller).
2. Add the unique constraint on intent ID.
3. **Prove it fires**: replay last night's message twice in staging and watch the second one get refused. A device that's never gone red is a belief.
4. Write `docs/poka-yoke/retro-2026-08-21-double-charge.md` with the class-sweep count.

Keep the "recent charge" check if you like, but label it what it is — a warning, not the fix.

I can write the retro doc and sketch the wrapper signature/migration if you point me at the payment worker repo.