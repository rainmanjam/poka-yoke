No — that guard is a symptom patch, not a fix, and the fact that this is the second time is itself diagnostic: whatever caught it last time didn't generalize, which means the last fix was aimed at the mistake, not the hazard.

**Defect**: 340 customers double-charged, refunded after the fact.
**Mistake**: the retry path called `charge()` again after the original attempt actually succeeded on Stripe's side (the timeout was on your side, not Stripe's).
**Hazard**: `charge()` can be called successfully without a caller supplying anything that makes the *operation* idempotent — only a heuristic post-hoc check for whether it *looks* like it was already called.

That's the part worth being precise about: the new check doesn't remove the hazard, it adds a second fallible query on top of it.

**Why "check for a recent charge with the same amount" isn't enough:**

1. **It's a TOCTOU race, and this incident's exact trigger reproduces the race.** Timeout → redelivery means two attempts *can* run concurrently (original worker still blocked on the Stripe response past the queue's visibility timeout, second worker already picked up the redelivered message). Both can query "any recent charge?", both see nothing yet, both proceed. The check only helps when the attempts are safely sequential — which is the one case you don't actually need protecting against.
2. **"Same amount" is the wrong key.** It has no relationship to *which* logical transaction this is. A customer legitimately charged twice for the same amount (repeat purchase, renewal at list price) now silently fails to charge the second time — you've traded a double-charge bug for a silent-undercharge bug, and this one has no refund trail pointing back to it because nothing errors.
3. **It's scoped to one call site.** If your queue redelivers on timeout, every other consumer that performs a non-idempotent side effect (send email, provision a resource, decrement inventory, issue a webhook) has the identical hazard sitting quietly, unexercised, until its own timeout day.

**What actually closes it (Control rung, not Detection):**
- Derive a stable idempotency key from something that already uniquely identifies the transaction — the queue message ID, or better, an order/invoice ID generated once upstream — and pass it as Stripe's `Idempotency-Key`. Stripe then refuses the duplicate at the API layer regardless of how many times or how concurrently you call it.
- Back it with a DB-level unique constraint (`orders.charge_id` or a `(order_id)` unique index on your charges table) so that even a bug in the idempotency-key logic can't produce two charge rows for one order — the database refuses it, not a query you have to remember to write correctly.
- Keep the "recent duplicate" check if you like, but as a monitoring signal, not the control.

**The step I'd actually push on next**, since this is a repeat: pull up every consumer on that queue and check which ones assume at-most-once delivery. Whatever the diff for this fix looks like, if there's no test that (a) delivers the same message twice and (b) asserts one charge, one order state, the fix hasn't been shown to work — it's been shown to compile.

Want me to look at the actual worker/queue code and draft the idempotency-key + unique-constraint change, and the redelivery test that proves it?