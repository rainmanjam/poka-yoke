No — the amount-match check is a patch on the symptom, not the hazard, and it will let this recur under the exact conditions that caused it.

**Defect:** 340 customers double-charged.
**Mistake:** the queue redelivered the message after a Stripe timeout, and the retry called the charge path again.
**Hazard:** the charge operation has no durable, atomic identity — nothing in the system (your code or Stripe) is told "this is attempt #2 of the same logical charge," so a second attempt is indistinguishable from a legitimate new one.

**Why the new check doesn't close that hazard**

"Look for a recent charge with the same amount before charging" is a check-then-act, not a constraint:

- **It's a race, and the incident condition is exactly the race window.** Queue redelivery under load frequently means two workers (or two overlapping attempts) both query "no recent match" before either charge lands, then both proceed. A read-then-decide check has no atomicity — it doesn't stop concurrent duplicates, only sequential ones with a large enough gap.
- **Amount is a proxy for identity, not identity.** Two legitimate charges for the same customer at the same amount close together (reordered item, split payment, retried after a decline) will get silently *dropped* — a new failure mode, and a quiet one, since nothing tells the customer or you that a real charge was suppressed.
- **It's tunable-fragile.** However you set "recent," it's wrong in one direction or the other: too wide and you eat legitimate charges, too narrow and the original bug still gets through.

This lands at Warning at best, and a leaky one — it's still possible, and possible silently in the drop case.

**What Control looks like here**

1. Assign a stable idempotency key to the *logical* charge when it's first decided (order ID, invoice ID, or a UUID persisted with the order before any charge attempt) — never derived from amount or a time window.
2. Pass that key as Stripe's `idempotency_key` — Stripe dedupes atomically server-side on retries.
3. Enforce it in your own ledger too: a unique constraint on `(account_id, idempotency_key)` on the charges table, so a duplicate insert fails at the DB layer regardless of timing. This is what actually removes the race — a constraint, not a query.
4. Make the idempotency key a required argument to the charge function, not optional, so no call site can invoke it without one.

**Before closing this out, two questions worth answering:**

- **The class sweep** — is the payment worker the only consumer on this queue, or do other consumers (emails, webhooks, ledger writes) also assume at-most-once delivery? If the queue redelivers, every consumer downstream has this hazard, not just this one.
- **Why did this happen twice** — what did the first incident's fix look like? If it was also a runtime check or an alert rather than a constraint, that's the actual pattern worth naming: fixes are landing at Detection/Warning tier instead of Control tier.

Want me to write this up as `docs/poka-yoke/retro-2026-08-22-double-charge.md` per the repo's convention, and/or find the queue's other consumers to confirm the sweep?