Short answer: **no.** The fix you shipped is a check-then-act race — it is the same hazard wearing a different coat, and it also covers only one of the sites where this mistake is available. Here's the retro, in the skill's shape.

## Defect / mistake / hazard

- **Defect**: 340 customers charged twice.
- **Mistake**: the redelivered message ran `charge()` a second time.
- **Hazard**: **a charge can be created without an idempotency key, and nothing at the Stripe or database layer refuses the second one.** The queue redelivering is not the bug — at-least-once delivery is the normal case. The system *permitted* a retry to become a second charge.

"Second time this has happened" is the tell: the first fix addressed the mistake, not the hazard.

## Why the new check is not enough (catalog hazard M5 + M2)

"Look for a recent charge with the same amount, then charge" is a `SELECT` followed by a side effect:

1. **It races.** Two workers pull the redelivered message and the original concurrently (exactly what happens after a timeout). Both see no recent charge; both charge. The window is the full Stripe round-trip — the one that just timed out.
2. **Timeout doesn't mean failure.** The first attempt timed out *client-side*; Stripe may have completed it. A "recent charge" lookup against your own DB won't see a charge you never got the response for. That is precisely the 340-customer case.
3. **Same amount ≠ same intent.** Two legitimate $20 orders inside the window get silently dropped — you've traded a loud duplicate for a silent lost sale. And it's a time-windowed heuristic that you'll tune, and re-tune.
4. **Single site.** It lives in this worker. Anything else that can reach `charge()` — an admin retry button, a backfill script, a cron, the other service — still has the mistake available.

Rung: this is **Detection at best**, bypassable by concurrency.

## Devices, by rung

| Device | Rung | Covers |
|---|---|---|
| `charge()` takes a **required** idempotency key (not optional) derived from the *order/intent ID*, not the message ID, and passes it to Stripe as `Idempotency-Key`. Stripe then returns the original result for a retry — including one whose first response you never received. | **Control** | every caller, including the timed-out one |
| A `payment_attempts` table with `UNIQUE (order_id)` (or `(account_id, idempotency_key)`), where the row is **inserted in the same transaction as the intent to charge**, before calling Stripe. A redelivery hits the constraint, reads the stored status, and reconciles instead of charging. | **Control** | every code path, every language, `psql` included |
| Bind the key to the payload (amount, currency, customer) — same key, different payload → error, not a silent no-op. | Warning | misuse of the key itself |
| Reconciliation job: Stripe charges per customer per order vs. your ledger; alert on >1. | Detection | anything the above misses; proves the device works |
| Regression test: deliver the same message twice, concurrently, assert one Stripe call. | Detection | this path |

Only the first two change the shape of the mistake. Required key is cheap; the DB constraint is what makes it durable against the next caller someone writes.

## What should have caught it, and didn't

Something to ask explicitly in your retro: why did the first incident's fix not produce the constraint? Usually the answer is "the key was added as optional to avoid touching callers" — which is the hazard reappearing as a convenience.

## Class sweep (do this before closing)

Grep for every external mutation reachable from a queue consumer, cron, or retry: emails, webhooks, refunds (your refund script from last night — was *it* idempotent?), inventory decrements, ledger writes. Count them and report the number; it changes what the fix is worth. If you point me at the repo I'll run `plugins/poka-yoke/scripts/detect_hazards.py --id M2` across it and list the sites.

## Verify before you call it closed

Replay the same message twice concurrently against staging and watch the second attempt get refused by the constraint — and a different-payload reuse get rejected. A device that has never fired is a belief.

**Recap**: the amount-lookup check is a race and a heuristic; it does not prevent recurrence. Install a required idempotency key on `charge()` (passed through to Stripe) plus a unique-constrained attempt row reserved before the call, sweep every other retryable side effect for the same shape, and prove the device fires. Next step on your side: share the worker/`charge()` code or repo path and I'll do the sweep and draft the constraint.