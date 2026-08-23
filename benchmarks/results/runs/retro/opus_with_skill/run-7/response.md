Using the poka-yoke `retro` mode. I couldn't write the doc to `docs/poka-yoke/` (write permission wasn't granted), so it's here.

## No — and the specific reason matters

**Defect**: 340 customers charged twice.
**Mistake**: the queue redelivered; the second invocation called `charge()` again.
**Hazard**: *a charge has no identity.* Nothing in the signature or the schema can distinguish "retry of charge X" from "a second, legitimate charge." That's hazard **M2 — non-idempotent retryable effect**.

Your check fails three ways, and the first is disqualifying:

**1. It is blind in exactly the scenario that caused the incident.** The check queries *your* database. The worker timed out *waiting on Stripe* — so attempt #1 was either still in flight or had already succeeded at Stripe with the response lost. Either way it hasn't written a charge row yet. Attempt #2 looks, sees nothing, charges. **This fix would not have prevented last night.**

**2. Check-then-act race (M5) + invariant enforced only in the app (F6).** Both attempts can run the `SELECT` before either runs the `INSERT`. `SELECT`-before-`INSERT` for uniqueness is the textbook signal. It passes every test and fails under the concurrency that produced the incident.

**3. "Same amount, recently" is a guess at identity, wrong in both directions.** False negatives: a cent of tax/FX difference, or a redelivery after the window (DLQ replay, backlog, manual re-run). False positives are worse — a customer legitimately buying two $9.99 top-ups gets *silently not charged*. You'd trade a loud, refundable defect for a quiet one with no alert and no row to reconcile.

By the ladder that's rung 2 at best.

## The device (Control)

1. **Key derived from business intent**, stamped by the producer at enqueue — order ID, not a UUID minted in the worker (regenerated on redelivery, buys nothing).
2. **Required, distinctly-typed parameter**: `charge(customer, amount, key: IdempotencyKey)`. Not `key: str | None = None` — an optional idempotency key is rung zero in a costume.
3. **`UNIQUE (customer_id, idempotency_key)`, reserved *before* the effect**: INSERT the pending row → call Stripe → update outcome. Inserting first is what closes the race; insert after and you've rebuilt it with a better index.
4. **Send the key to Stripe** as the `Idempotency-Key` header. This is the piece that covers the timeout: your constraint stops *your worker* charging twice; Stripe's key stops the charge that already landed when you never saw the response.
5. **Replay the stored result on conflict** — don't just reject. A caller that gets a constraint violation has learned nothing about whether attempt #1 worked; it nacks, redelivers, and you have a poison loop.
6. **Then delete the amount check.** Left alongside, it silently suppresses legitimate repeat purchases forever, and looks like it's working.

`★ Insight ─────────────────────────────────────`
The reserve-then-act ordering is the whole trick. A unique constraint checked *after* the external call is a detection device; the same constraint reserved *before* it is a control device. Same DDL, different rung.
`─────────────────────────────────────────────────`

## Class sweep — this is where the value is

Redelivery is a property of **the queue**, not the payment worker. Every consumer performing an effect outside its own transaction has this hazard *right now*: refunds (same bug, harder to claw back), payouts, ledger writes, outbound webhooks (you've exported the bug to customers), emails, inventory decrements, subscription provisioning. Plus every other `charge()` caller, the DLQ replay tooling, and any admin "re-run this job" button.

I can run `detect_hazards.py --id M2 --id M5` over the service repo if you point me at it — it isn't in this working directory.

## Why it's the second time

The first fix was path-level. The one you just shipped is path-level. There will be a third, in a different consumer.

The structural device: **the consumer test harness delivers every message twice, always** — not opt-in, the default of the base class. A non-idempotent handler then fails CI the day it's written. Pair it with a handler registration that won't compile/boot without a `key_for(msg)` extractor. That's the class-level Control, and the test-harness half is cheap.

## Verify before closing

Two consumers, same message, concurrent, Stripe stubbed to hang past the timeout → assert exactly one charge. Then two *genuinely distinct* orders, same customer, same amount, seconds apart → both must succeed. Break the constraint on purpose, watch it go red, put it back.

---

**One decision I need from you**, because everything above hangs on it: what's the stable business identity of a charge in your domain — order ID, invoice ID, payment-intent ID, or a composite? It has to be identical across redeliveries and distinct across legitimate repeat purchases, and only you know whether e.g. a subscription renewal reuses the order ID. If you sketch `key_for(message)` (5–10 lines) I'll build the constraint, the migration, and the double-delivery test around it.