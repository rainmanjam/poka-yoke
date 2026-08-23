No — the check you added closes the exact bytes that broke last night, but it's a rung-3 (Detection) patch on a rung-0 hazard, and it's fragile enough on its own to cause a *new* kind of failure quietly.

**Separating the three things:**

- **Defect**: 340 customers double-charged in one worker run; refunded after the fact.
- **Mistake**: the queue redelivered the payment message (correct at-least-once behavior) and the retry called `charge()` again.
- **Hazard**: `charge()` has no idempotency guarantee — nothing in the code, the database, or Stripe's own API ties "one logical charge" to "at most one actual charge." That hazard is still there after your fix.

**Why the "recent charge, same amount" check isn't enough:**

1. **TOCTOU race.** If two redeliveries land close together (queues don't guarantee spacing), both can run the lookup before either has written the new charge. The check passes for both. This is the *same class* of bug that caused the incident — a read-then-act gap — just moved one level up.
2. **Wrong match key.** Amount + recency isn't a stable identity. Two different legitimate charges of the same amount to the same customer in a short window (two separate line items, a retry the customer intentionally initiated) will now silently get skipped — you've traded "customer charged twice" for "customer not charged and nobody notices," which is worse because it's invisible instead of loud.
3. **It's bolted onto one call site.** It doesn't stop the same shape of mistake anywhere else the same non-idempotent pattern exists.

**The Control-rung fix:** derive a stable idempotency key from the *business object being paid for* (order ID / invoice ID — not the queue message ID, not "amount + timestamp"), and:
- pass it as Stripe's native `idempotency_key` on `charges.create` — Stripe itself will return the original charge instead of creating a second one, atomically, on their side
- add a unique constraint on that key in your own ledger table, so the guarantee holds even if a code path ever bypasses Stripe's dedup

That's the "idempotency-key scope" decision that was still open from earlier — my recommendation: scope it to the durable business identifier (order/invoice ID), not the attempt or message ID. An attempt-scoped key just relocates the race to "did this attempt already run," which is the same TOCTOU problem in a new shape. An order-scoped key makes retries — whether from your queue or from Stripe's own webhook retries — collapse onto the same charge by construction, no lookup required.

**"Second time it's happened" — ask why nothing caught it.** Was there a test that simulates redelivery (call the handler twice with the same message) before this shipped? If not, that's the missing device: a regression test that proves `charge()` is a no-op on replay, run against the real handler, not a mock.

**Class sweep** — from the earlier pass on this: any other queue consumer with a side effect that isn't naturally idempotent has the same hazard — receipt emails, outbound webhooks, ledger/balance writes. Redelivery will hit those the same way it hit Stripe. Worth listing those consumers and confirming each either has its own idempotency key or is provably safe to run twice (e.g., a `SET` instead of an `INCREMENT`).

Want me to draft the idempotency-key + unique-constraint change against your actual worker code, and a redelivery regression test to go with it?