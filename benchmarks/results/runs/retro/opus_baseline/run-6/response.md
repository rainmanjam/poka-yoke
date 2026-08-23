No — and the way it fails is the same way the original failed.

**Your new check is a read-then-write race.** The worker reads "is there a recent charge?", gets no, then charges. Redelivery on timeout means the first attempt is *still in flight* at Stripe — that's the exact window where the lookup returns nothing. The check is blind in precisely the scenario that caused the incident. It'll reduce the count and make the next occurrence smaller and harder to spot.

The amount heuristic has a second problem: it's wrong in both directions. A customer legitimately buying the same $12 item twice gets silently under-charged (much harder to detect than an over-charge), and any duplicate with a differing amount — tax recalc, currency rounding — sails through.

**Separating the three things:**

- **Defect:** 340 customers charged twice.
- **Mistake:** the retry path called `charge()` again with no dedupe token.
- **Hazard:** *charging is not idempotent, and nothing in the type system, the API call, or the database prevents a second charge from existing.*

The whys bottom out at a missing constraint, not a missing check: Stripe's `Idempotency-Key` header is optional, so `charge()` compiles and succeeds without one.

**What actually closes it — two devices, both Control rung:**

1. **A deterministic idempotency key derived from business intent** — the order ID or payment-attempt ID, not a UUID generated inside the worker. Same message redelivered → same key → Stripe returns the *original* charge instead of making a new one. This works during the in-flight window, which your check cannot.
2. **A unique constraint on your own charges table** keyed on that same identifier. This matters because Stripe's keys expire after 24h — a message replayed from a DLQ two days later is unprotected. The database is the backstop.

Then make it unavailable: `charge()` should not accept an optional key. Type the parameter as required so the timeout path can't be written without one.

**The part that matters most, given this is the second time.**

At-least-once delivery isn't a payment property — it's a property of your queue. Every consumer on it has this hazard. Payments announced itself because money is visible. The ones that won't announce themselves: duplicate emails, webhook re-fires to customers, double ledger entries, inventory decremented twice, provisioning run twice. If the first incident was also fixed at one call site, that's the pattern to break — you're fixing paths, and the hazard is a property.

**Why nothing caught it:** there's no test that delivers a message twice. That's a cheap, high-value device — a consumer contract test that replays every message and asserts identical end state, run in CI.

---

One decision is genuinely yours and shapes everything else: **what the idempotency key is scoped to.** Order ID means a customer can never be charged twice for one order, but legitimate retries of a *changed* order are blocked. Payment-attempt ID is safer for retries but requires the attempt row to exist before Stripe is called. Which does your checkout flow support?

Want me to write this up as `docs/poka-yoke/retro-2026-08-22-double-charge.md`?