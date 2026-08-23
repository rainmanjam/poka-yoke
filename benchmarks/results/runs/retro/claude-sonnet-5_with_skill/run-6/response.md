Applying the **retro** mode — this is exactly its target case: a defect that already cost something real, described as "the second time," which is the strongest signal in the skill to push for the top rung rather than settle.

## Short answer

No, it's not enough. What you shipped is a rung-2 **warning** dressed as a fix, and it's a *leaky* one — it has a race condition that can fail on the exact scenario that caused this incident.

## Why the interim check doesn't hold

Separate the three things:

- **Defect**: 340 customers double-charged.
- **Mistake**: the queue redelivered the payment message after a Stripe timeout, and the worker processed it as a brand-new charge.
- **Hazard**: the charge path has no stable identity — nothing ties "this specific payment attempt" to "have I already done this?" in a way the system enforces. "Recent charge, same amount" is a *guess* standing in for that missing identity.

Two concrete problems with "check for a recent charge with the same amount":

1. **TOCTOU race.** If the queue redelivers fast (which is exactly what happens on a timeout-triggered redelivery — the second attempt often lands while the first is still in flight), both workers can run the "any recent charge?" check before either has written a charge record. The check-then-act gap is unguarded. This is the same failure shape as the original bug, one layer up.
2. **Wrong key.** "Same amount, recent" is a proxy, not an identity. It produces false negatives (a customer legitimately charged the same amount twice in quick succession — e.g., two separate small purchases — gets silently blocked) and, more importantly, it doesn't actually derive from anything unique about *this delivery attempt*, so it can't give you a hard guarantee, only a probabilistic one.

That's rung 2 at best (self-check, informative, after the fact), and it's a weak rung 2 because the check itself isn't atomic with the charge.

## The constraint that's actually missing

Ask why until you hit a constraint, not a human quality:

> Redelivery → worker charged twice → worker had no way to recognize "I've already handled this message" → *why not?* → the charge call has no idempotency key tied to the message → *why not?* → nothing requires one — Stripe supports idempotency keys, but the worker doesn't pass one, and there's no unique constraint on your own ledger either.

That's the hazard: **charge issuance is not idempotent, at any layer.** The fix that reaches Control rung:

- Pass a **Stripe idempotency key** derived from a stable identifier of the payment attempt (e.g., `order_id` or `payment_attempt_id`, not a timestamp or amount) on every `charge()` call. Stripe deduplicates atomically on their side — this closes the race your amount-check can't.
- Add a **unique constraint** on your own ledger table, e.g. `UNIQUE(order_id)` or `UNIQUE(idempotency_key)`, so even if two workers both try to record a charge, only one write succeeds — the DB enforces it, not application logic.
- Make the idempotency key a **required** argument to whatever function issues the charge, not optional. If it's optional, someone will eventually call it without one, and you're back here.

That combination is two Control-rung devices (Stripe-side dedup + DB constraint) plus a signature change that makes the mistake unrepresentable at the call site — no reliance on a fuzzy runtime heuristic.

## The step that's easy to skip: sweep for the class

You said "this is the second time." That's the tell that the hazard isn't local to the payment worker — it's **"this queue delivers at-least-once, and consumers assume at-most-once."** Every other consumer of that queue with a side effect has the same exposure:

- Does the email/receipt sender re-send on redelivery?
- Does the webhook dispatcher re-fire?
- Does anything else write to the ledger, adjust inventory, or call an external API from this queue?

If you haven't checked those, the next incident is already sitting in one of them. I'd treat "make every consumer of this queue idempotent, or prove it already is" as the actual scope of this retro, not just the payment worker.

## Before closing it out

Prove the fix, don't just believe it: replay a message twice against the new path and confirm the second attempt is rejected by the constraint (not just "looks skipped" in logs), and confirm a genuinely new charge still goes through.

Want me to write this up as `docs/poka-yoke/retro-2026-08-22-double-charge.md` in the format the skill specifies, or help you find the other queue consumers that share this hazard?