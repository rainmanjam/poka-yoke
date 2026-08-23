No — and the specific way it's insufficient is worth being precise about, because it's the same shape as the first incident.

## The check is blind to the exact failure that caused this

Your worker timed out *waiting on Stripe*. The charge succeeded at Stripe; only the response was lost. So at the moment attempt #2 runs its lookup, your database has no charge row — you write that row *after* Stripe returns, and it never returned. The check queries a record that by definition does not exist in the one scenario it was built to catch.

Even if the timing were kinder, it's a check-then-act race: two consumers can both read "no recent charge" before either writes. And `(amount, recent)` isn't identity — it blocks a customer legitimately buying the same thing twice, and misses a retry where tax or proration shifted the total by a cent.

That's Warning rung at best. It fires sometimes, silently, on a heuristic.

## Three separate things

- **Defect**: 340 customers charged twice.
- **Mistake**: the retry path called charge again with no idempotency key.
- **Hazard**: *your charge path has no representation of "this payment was already attempted" that survives the process dying mid-flight.* Nothing — no type, no constraint, no API parameter — makes the second call a no-op.

The hazard is why this is the second time. Both fixes so far were at the call site.

`★ Insight ─────────────────────────────────────`
At-least-once delivery is your queue's *contract*, not its bug. Under that contract, a non-idempotent consumer isn't unlucky — it's incorrect. That reframes the scope: this isn't a payments bug, it's every consumer on that queue.
`─────────────────────────────────────────────────`

## Control-rung devices

1. **Stripe `Idempotency-Key` header**, derived deterministically from the business entity (order ID), not generated at call time. This is the only device that works when your process dies mid-request, because the key travels *with* the request and Stripe arbitrates. 24h window.
2. **Unique constraint** on `(order_id)` in a charge-attempts table, row inserted **before** calling Stripe. The database becomes the arbiter instead of a `SELECT`. This is your backstop past Stripe's 24h.
3. **Make the key non-optional in the type** — an internal `charge()` that cannot be called without one, and a lint/CI rule forbidding the Stripe client from being imported outside that one module. Otherwise the next call site re-opens the hazard.
4. **Daily reconciliation**: Stripe charges vs. your ledger, alert on any `order_id` with >1 succeeded charge. Detection rung, but it would have caught this in hours rather than overnight.

## Class sweep — the step that decides whether there's a third time

Before writing code: what else consumes that queue? Emails, webhooks, ledger writes, provisioning. Each one that isn't keyed has this same hazard today.

**The decision I need from you:** what business entity defines "the same payment"? Order ID is the obvious answer, but it breaks if an order can legitimately be charged more than once — partial captures, retries after a card decline, subscription renewals against a fixed subscription ID. Pick wrong and the constraint either lets doubles through or refuses a legitimate second charge in production at 2am. What's the coarsest identifier in your model that should only ever be charged once?