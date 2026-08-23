No — and the reason is specific enough to be worth stating precisely.

## The three things

- **Defect**: 340 customers charged twice.
- **Mistake**: the retry path called Stripe again for work that had already been submitted.
- **Hazard**: a timeout is recorded as "did not happen," and `charge()` accepts a second identical call and succeeds.

## Why the new check doesn't close it

Your check reads your own database, then decides. It is blind in exactly the case that caused this incident. Attempt 1 timed out — meaning your worker never got a response, meaning **it wrote nothing**. Attempt 2 queries for a recent charge, correctly finds none, and charges. The check passes precisely when the money has already moved.

It also has a race: with a redelivery window shorter than the Stripe call, both attempts can query before either writes.

And it fails the other way too. A customer who legitimately buys the same $49 thing twice in a minute gets silently refused. You've traded a loud failure for a quiet one.

Three more edges: "recent" is an unbounded guess (SQS visibility timeout at 5 min beats a 60s window); the check guards one call site, not the class; and it can't fire at all for the charge that's still in flight.

## The device

Stripe idempotency keys — with one detail that is the whole thing:

**Derive the key from the work item, not at call time.** Generate it when the intent is created (order line, invoice, payment request), persist it on the job payload, so every redelivery of that queue message carries the *same* key. Stripe then returns the original charge instead of creating a second one, even when your first response was lost. That's a Control-rung device: the duplicate becomes unrepresentable at the boundary you don't own.

Back it with a `UNIQUE (account_id, idempotency_key)` constraint so your own DB refuses the double-write independently.

`★ Insight ─────────────────────────────────────`
The deeper hazard is a type: `charge()` returns `Success | Failure`, but a timeout is neither — it's `Unknown`. Code with no way to represent Unknown coerces it to Failure, and Failure means "safe to retry." Add the third case and the compiler forces every caller to decide what Unknown means.
Unknown resolves by *reconciliation* (query Stripe by key), never by retry.
`─────────────────────────────────────────────────`

## Why it's the second time

That's the actual finding. The first fix was almost certainly also rung 3 — a check, at one call site. Point-fixes at the detection rung don't remove hazards, so the class stayed open and picked a different door.

**Two things I'd want your call on**, since they're judgment, not mechanics:

1. What's the stable identity a key derives from — order line? invoice? something else that survives a retry but differs between two genuine purchases?
2. On `Unknown`, do you reconcile inline (blocks the worker) or park to a queue (customer waits)?

Point me at the payments repo and I'll sweep every other call site where an unkeyed charge is still reachable, and write the retro up properly.