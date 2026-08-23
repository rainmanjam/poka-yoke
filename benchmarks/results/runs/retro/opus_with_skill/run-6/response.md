I read the router, it pointed to `retro` (something already broke, twice), and I read that plus the hazard catalog. Here's the analysis.

## No. The check you added is the same hazard wearing a different shape.

**Separating the three things** — conflating these is why it's the second time:

- **Defect**: 340 customers charged twice.
- **Mistake**: the retry path called `charge()` again.
- **Hazard**: `charge()` can be called twice with the same intent and succeed both times. Nothing in the type system or the database forbids it.

Your fix addresses the *mistake* on one code path. The hazard is untouched.

**The why-chain:** double charge → queue redelivered → second attempt charged → the worker had no way to say "this is the same charge as before" → **charge identity exists nowhere except in the worker's head.** That's the missing constraint.

## Why the recent-charge check specifically fails

It's hazard **M5, check-then-act** — you replaced a duplicate-charge bug with a race that produces the same defect less often. Both workers `SELECT`, both see no recent charge, both call Stripe. A timeout is *precisely* the condition that widens that window. It'll fire again, more rarely, and be harder to diagnose.

Two more problems: matching on *amount* silently blocks a customer legitimately buying the same thing twice, and "recent" is a magic window that's wrong at both ends. And it's rung 3 at best — detection, after the fact, on the one path you thought of.

## The device

Required idempotency key, backed by a unique constraint. Per the catalog (M2), the constraint alone is necessary but not sufficient:

| Piece | Why |
|---|---|
| Key is a **required** parameter of `charge()` | An optional key is rung zero in a costume — the retry path is exactly the caller that'll omit it |
| `UNIQUE (entity, idempotency_key)` in the schema | App-level checks race and are bypassed by every script and `psql` session (F6) |
| Key reserved **in the same transaction as the effect** | Otherwise you've rebuilt the race one layer down |
| Key bound to the request payload | A different amount under a reused key must error, not silently no-op |
| Stored result **replayed** to the second caller | Critical: a retry that gets a constraint violation has learned nothing about whether the first charge worked. Pass the same key to Stripe too — they dedupe on it |

That's **Control**. The mistake stops being possible rather than being caught late.

## The sweep is the part that answers "second time"

The class isn't `charge()`. It's **every consumer on that queue that performs a non-reversible external effect** — emails, webhooks out, ledger entries, provisioning, Stripe's own webhook handler. At-least-once delivery is the contract; every one of those consumers is one timeout from its own version of last night. Redelivery didn't malfunction, it did its job.

I can't sweep your repo from here — this working directory is the poka-yoke repo itself. Point me at the payment service and I'll run `detect_hazards.py --id M2` plus a manual pass over the consumer registrations, and report the count. That number is what makes the case for doing this properly instead of patching again.

## Before you close it

Reproduce the incident against the new device: fire the same message twice concurrently, watch the second attempt get refused *and* return the first attempt's result. A device that's never been observed to fire is a belief.

---

**One decision is genuinely yours, and it's the same one that blocked this earlier in the session:** what scopes the idempotency key. Order ID is the obvious candidate, but it breaks if a single order can legitimately produce multiple charges (partial capture, split shipment, retry after a genuine decline). The alternative is a key minted at intent-creation time and carried on the queue message.

Which is it for your domain? That choice determines the unique constraint, so it's worth getting right before there's a migration to undo.