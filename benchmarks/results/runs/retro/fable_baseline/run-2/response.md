No. The fix you shipped is a **detection**-rung device dressed as a control, and it has holes of its own. Short version: the second time is the tell — the hazard was never removed, only one path patched.

## Separate the three things

- **Defect**: 340 customers charged twice.
- **Mistake**: the redelivered message called `charge()` again.
- **Hazard**: **a charge can be created without an idempotency key.** Stripe has supported `Idempotency-Key` on every POST for years precisely for this case; your code lets a charge exist without one. That's the system property. "The worker timed out" and "the queue redelivered" are not bugs — at-least-once delivery *guarantees* this will happen again.

## Why the "recent charge with same amount" check isn't enough

1. **It's a read-then-write race.** Two workers picking up the same message (or the original still running when redelivery fires — which is exactly what a timeout means) both see "no recent charge" and both charge. The original failure mode reproduces.
2. **False positives.** A customer legitimately buying the same amount twice within the window gets silently not-charged. You've traded a loud defect for a quiet one, and quiet ones are worse.
3. **The window is a guess.** Too short and it misses; too long and #2 bites.
4. **It relies on your DB reflecting Stripe.** The timeout case is *precisely* when Stripe succeeded but you never recorded it. A local-state check is blind to the case that caused the incident.
5. **It protects one worker.** Anything else that calls Stripe — refunds, subscription changes, a backfill script — is still unguarded.

## What Control looks like

| Device | Rung | Covers |
|---|---|---|
| Idempotency key derived from the *intent* (e.g. `order_id:attempt-purpose`), passed on every Stripe POST. Stripe returns the original result instead of a second charge, **including for the timed-out request** | Control | this worker |
| Make the key a **required** parameter on your Stripe wrapper — not optional-for-backward-compat. Delete the raw client export so nobody bypasses it | Control | every caller, present and future |
| DB `UNIQUE (idempotency_key)` on your payments table, inserted *before* the Stripe call (`pending`), updated after | Control | the race; also gives you a reconciliation list of `pending` rows to check against Stripe |
| Stripe `payment_intent.succeeded` webhook as source of truth; daily reconciliation of your ledger vs Stripe's | Detection | the "Stripe succeeded, we don't know" gap |
| Test: simulate timeout → redelivery, assert exactly one Stripe call with the same key | Detection | regression |

## The class sweep (you need to do this one)

Grep every Stripe POST and every consumer of that queue. Ask for each: *what happens if this message is delivered twice?* If the answer isn't "nothing," it has the same hazard. The first incident was probably a different consumer with the same shape — that's what "second time" usually means.

## Honest recap

- The refund and the amount check were the right *immediate* action; they are not the fix.
- The hazard is "idempotency is optional." Until `charge()` cannot be called without a key, this is an accepted risk, not a resolved incident.
- If you want, point me at the payment service repo and I'll run the class sweep and draft the wrapper + unique constraint + the regression test that proves redelivery produces exactly one charge.