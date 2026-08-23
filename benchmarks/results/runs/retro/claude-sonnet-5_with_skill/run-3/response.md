No — the fix you shipped is a warning-rung patch on top of a control-rung problem, and the shape of it means it can still fail exactly the same way.

**Defect:** 340 customers double-charged.
**Mistake:** the redelivered message called the charge path a second time.
**Hazard:** the charge path has no way to know "have I already done this specific charge" — it can only guess after the fact.

Your fix ("look for a recent charge with the same amount before charging") is a check-then-act against Stripe/your DB, and that's the same shape of bug in miniature:

- **TOCTOU race**: if the timeout was long enough to trigger a redelivery, it's plausible for two workers (or two retries) to both run the "any recent charge?" query, both see nothing yet, and both charge. The window you're trying to close is exactly the window the check reads through.
- **Weak identity**: "same amount" isn't "same transaction." Two legitimate charges for the same customer at the same amount close together (renewal + add-on, retried failed charge with same price) get blocked. Meanwhile a charge that's logically the same attempt but computed a slightly different amount (proration, currency rounding) sails through.
- **No memory of the original request**: nothing ties the two delivery attempts together as *the same charge attempt*. You're reconstructing intent from a query instead of carrying an identity forward.

Why is there no such identity? Because the charge call was never given one — that's the missing constraint. Ask it one more level: why has this shape survived two incidents? Because nothing in the pipeline stops a charge from being issued without one — there's no required idempotency key and no database constraint that would refuse a duplicate outright.

**The control-rung fix:**
1. Generate an idempotency key once per logical charge attempt (e.g. `order_id` or `invoice_id`, not a random UUID per call) and pass it as Stripe's `Idempotency-Key`. Stripe will then return the *original* charge result on redelivery instead of creating a new one — this is enforced by Stripe itself, not by your query.
2. Back it with a unique constraint in your own DB on `(order_id)` or `(idempotency_key)` in the charges table, and write the row in the same transaction as the Stripe call's result. That gives you a second, independent control if the Stripe key is ever missing or mishandled.
3. Delete the "same amount" heuristic once (1) and (2) are in — it's now dead weight that can misfire (block legitimate same-amount charges) without adding protection.

That gets you from rung 2 (informative, racy) to rung 1 (control): the second delivery attempt isn't "detected as probably a dupe," it's structurally the same request and returns the same result.

**Before you call it closed:** reproduce the incident against the new code — fire the same charge request twice concurrently — and show it produces one charge, not "probably no charge." A device that hasn't been watched to fire is a belief, not a control, and you said yourself this is the second time.

**Worth checking now, since this is #2:** what did the *first* incident's fix look like, and is it still in place? And are there other queue consumers in this system with the same non-idempotent shape (any other worker that does "act on message" without a dedup key) — that's usually where a second occurrence like this is telling you the class is bigger than one worker.

Want me to help design the idempotency-key + constraint shape for whatever your stack is?