Short answer: **no.** The refunds fixed the defect. The "recent charge with the same amount" check is a warning-rung heuristic that still leaves the hazard open — and it's the same class of fix that didn't hold the first time.

## The three things, separated

- **Defect:** 340 customers charged twice.
- **Mistake:** the retry path called Stripe's charge endpoint a second time for the same intent.
- **Hazard:** *a charge can be sent to Stripe without an idempotency key, and nothing refuses it.* That property is still true after your fix.

## Why the new check isn't a device

The lookup-before-charge has four holes, each of which is exactly the shape of "the next incident":

1. **It's a race.** The timeout case is the *only* case that matters, and it's the one where the first attempt may still be in flight when the redelivered message arrives. Attempt 1 hasn't written its charge record yet (it's waiting on Stripe), attempt 2 looks, finds nothing, charges. The check passes *because* of the condition it was meant to catch.
2. **Same-amount is the wrong key.** Two legitimate $9.99 charges in a window get blocked; a retry whose amount was recomputed (tax, FX, a coupon) gets through.
3. **It looks in the wrong place.** If the worker timed out, the charge may exist in Stripe and *not* in your DB. Your local table is the one source that's guaranteed stale in this scenario.
4. **It only covers this worker.** Any other path that charges — a retry script, an admin tool, a second service — still has the mistake available.

## What a Control-rung fix looks like

Stripe already ships the device: the `Idempotency-Key` header. Same key → Stripe returns the original result, never charges twice — including when the first request is still in flight.

- **Derive the key from the business event, not the attempt** — e.g. `order_id` or `invoice_id` + `attempt purpose`. Not a UUID generated inside the worker (a redelivered message would generate a fresh one).
- **Make it impossible to omit.** Wrap the Stripe client so `charge()` has no signature without a key — a required parameter or a wrapper type that can only be constructed with one. The hazard was "optional"; the fix is "required by the compiler/linter", not "remembered by the next engineer."
- **Back it with a DB unique constraint** on `(customer_id, idempotency_key)` written *before* the Stripe call, in the same transaction that enqueues/claims the message. That closes the race Stripe's key doesn't cover (your own duplicated bookkeeping).
- **Fix the timeout handling too:** a timeout is *unknown outcome*, not failure. The retry should re-send with the same key and read the result, not treat the first attempt as if it never happened.

## The escape question

Why did nothing catch it — twice? Likely: no test that delivers the same message twice and asserts one charge, and no reconciliation comparing Stripe's charge list against your ledger. Add both (Detection rung), but don't let them be the *only* thing added this time.

## Sweep — the step that gets skipped

Before closing this, grep for every call into the Stripe client (and any other payment/side-effect call made from a queue consumer — emails, webhooks, ledger writes). Every one without a required idempotency key is the same hazard wearing a different name. Report the count; "the same hazard exists at N other sites" is what justifies the wrapper over a one-line patch.

## What I'd write in the retro

| Device | Rung | Covers |
|---|---|---|
| Stripe wrapper with required, event-derived idempotency key | Control | every charge path |
| Unique constraint on `(customer_id, idempotency_key)` | Control | local double-bookkeeping + race |
| Test: redeliver same message twice → exactly one charge | Detection | this path |
| Nightly Stripe↔ledger reconciliation alert | Detection | anything else |
| "Recent same-amount" check | *retire it* — false positives on legitimate repeat charges, false negatives on the race |

Then prove it: replay the duplicate message against the new wrapper and watch it refuse. A device that has never fired is a belief.

If you want, paste the worker and the Stripe client wrapper and I'll run the sweep and draft the wrapper signature against your actual code.