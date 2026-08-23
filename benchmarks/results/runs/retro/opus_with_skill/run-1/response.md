No — and specifically, that check cannot fire in the case that caused this incident.

## The three things

- **Defect**: 340 customers charged twice.
- **Mistake**: the redelivered message ran the charge path a second time.
- **Hazard**: `charge()` carries no identity, so it can be called twice with the same intent and succeed twice. At-least-once delivery becomes at-least-once charging.

## Why chain

Worker timed out → queue redelivered (correct — at-least-once is the contract, not the bug) → second attempt charged → nothing tied attempt 2 to attempt 1 → **the charge call has no idempotency key, and nothing requires one.**

## Why the recent-charge check doesn't close it

Three independent failures, any one fatal:

1. **It reads state the timeout prevented from being written.** A timeout means *outcome unknown* — Stripe took the charge, your worker died before recording it. The query finds no recent charge and charges again. That is exactly last night's shape.
2. **Check-then-act race** (M5). Two consumers pass the check concurrently, both charge.
3. **Amount + window is a heuristic.** False positives block a customer legitimately buying the same-priced item twice; false negatives on any amount drift (tax, partial capture, FX).

Rung: **Warning at best**, and one that stays silent in the failure mode it was written for.

## The device (Control)

- **Required** idempotency key in the signature — not `Optional`, no default. An optional key is rung zero in a costume.
- **Derived from the queue message's stable delivery-independent ID**, not generated in the handler. A UUID minted at handler start is fresh on every redelivery and buys nothing.
- **Passed as Stripe's `Idempotency-Key`.** Stripe replays the original response, so attempt 2 *learns what attempt 1 did* instead of getting a constraint violation and guessing.
- **Unique constraint on `(charge_scope, idempotency_key)`**, reserved in the same transaction as recording the charge.
- **Timeout ≠ failure.** Reconcile by key; never re-decide.

The constraint alone isn't sufficient — rejecting a duplicate isn't the same as being idempotent. The key must be bound to the payload (same key + different amount = error, not silent no-op) and the stored result replayed.

## Class sweep — the step that matters most here

I can't run it; this repo isn't your payments service. Point me at it and I'll run `scripts/detect_hazards.py --id M2`. Manually, search for every at-least-once consumer with an external effect: **refunds** (including the 340 you just issued — was that job retry-safe?), payout creation, subscription create/cancel, transactional email, webhook fan-out, inventory decrement. Plus every signature with an optional idempotency key.

## The "second time" is its own finding

Ask what the previous incident's fix was. If it was also an application-level check, the pattern isn't payments — it's that your retros terminate at informative inspection instead of at a constraint. That's the thing to fix once.

---

**Your call, and it decides whether the device works:** what is the stable key? Options: the queue message/dedup ID (survives redelivery, dies if a *new* message is enqueued for the same intent), or a domain key like `invoice_id:attempt_period`. And: same key, different amount — hard error, or replay the original? Tell me which and I'll write the retro to `docs/poka-yoke/retro-2026-08-22-double-charge.md` with the device table and a failing-first verification test.