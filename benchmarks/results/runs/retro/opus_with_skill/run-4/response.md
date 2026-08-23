The write was blocked (no permission granted in this session), so here it is inline.

## No — the check you added is not a device, and it can't see the case that caused this

**Defect**: 340 customers charged twice.
**Mistake**: the worker ran the charge effect a second time for the same business intent.
**Hazard**: the charge is not idempotent and nothing *requires* it to be — plus a timeout leaves the first attempt's outcome **unknown**, so no amount of inspecting local state can resolve it.

That last part is why the recent-charge check fails. It's `if (!exists(x)) create(x)` — hazard M5, check-then-act — and it breaks three ways:

- **It races.** Two consumers on the redelivered message both SELECT, both see nothing, both charge.
- **It's blind to your actual incident.** Attempt 1 *timed out*. Stripe may have charged; you wrote no row. The check queries a table that is empty during exactly the window that matters.
- **It adds a new silent defect.** "Recent + same amount" matches legitimate repeat purchases. It will now refuse real payments, quietly.

Rung 3 at best. You have Control available, and after 340 real charges you have the strongest evidence you'll ever get for paying for it.

## Why it was possible

Charged twice → queue redelivered → **at-least-once is the contract**, that will keep happening → the effect wasn't tied to the intent → the charge call carries no idempotency key → **nothing at compile time or in the schema requires a charge to be idempotent.** That's a missing constraint, which is fixable.

## The device

| Device | Rung |
|---|---|
| **Required** (not optional) idempotency key on the charge path | Control |
| `UNIQUE (customer_id, idempotency_key)` in your schema | Control |
| Key reserved in a committed transaction *before* the Stripe call | Control |
| Same key sent as Stripe's `Idempotency-Key` header | Control |
| Reconciliation: >1 succeeded charge per intent → page | Detection |

Two things make or break this:

**The key derives from the intent, not the attempt.** A per-attempt UUID reproduces your bug exactly — the redelivery mints a new one. Use the invoice/order/period id.

**The constraint alone is insufficient.** A retry that gets a constraint violation has learned nothing about whether attempt 1 worked. The sequence must be: INSERT attempt row (`pending`, key, payload hash) and commit → on conflict read the existing row → if `succeeded`, replay the stored result; if `pending`, **call Stripe again with the same key** (safe by construction); if the payload hash differs, error. That `pending` branch is what resolves your timeout. Unknown outcomes can't be resolved by looking — only by an operation that's safe to repeat.

## This is the second time — so the sweep is the real finding

The hazard isn't in the payment worker. It's the delivery contract: at-least-once, consumed by handlers that assume exactly-once. **Every consumer on that queue** is a duplicate waiting for a timeout — emails, webhook dispatch, ledger writes, provisioning, credit grants. Also: inbound Stripe webhooks (redelivered on the same contract), double-submittable API paths, and backfill scripts that re-issue effects.

Fixing this at one call site is how you get a third incident.

**What was the first incident?** If it was this same class, that's the headline: the class was closed at one site and left open everywhere else.

## Before you close it

Replay the identical message twice in staging; assert one charge at Stripe. Then drop the unique constraint and watch that test go red — a device never observed to fire is a belief, not a control.

---

Two things I need from you:

1. **The key's scope** — what business fact defines "the same charge"? Invoice id is the usual answer, but if you support partial captures or retried failed payments on the same invoice, it needs a period or attempt-group component. This is the decision the whole fix rests on and it depends on your billing model, not on general principles.
2. **Repo access** — the worker isn't in this repo, so I couldn't run the class sweep. Point me at it and I'll run `detect_hazards.py --id M2 M5` across the consumers, and save this retro to `docs/poka-yoke/` there.