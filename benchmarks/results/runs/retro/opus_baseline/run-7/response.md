Their payment worker isn't in this repo — what's here is `benchmarks/fixtures/payments.ts`, which happens to contain the same shape as a fixture. So the analysis below is about the system you described, not code I read.

**Short answer: no, and it fails hardest in exactly the scenario that caused the incident.**

## Why the dup-check isn't enough

**1. It's a TOCTOU race.** Attempt 2 runs `SELECT recent charge` while attempt 1 is *still in flight at Stripe* — that's why it timed out. There's no row to find yet. The check reads state the first attempt hasn't written, so it returns "no recent charge" and charges. The window it's blind to is precisely the timeout window.

**2. "Same amount + recent" is a proxy for identity, not identity.** Two legitimate $9.99 purchases inside the window now get one silently swallowed. You've traded a double-charge for a missing-charge, which is quieter and worse. And "recent" is a tunable that will be wrong at some traffic level.

**3. Wrong rung, wrong scope.** It's a Detection-rung guess living in one function. Every other caller of the charge path, and every other consumer on that queue, still has the hazard.

## The three things, separated

- **Defect** — 340 customers charged twice.
- **Mistake** — the redelivered message was processed as a new request.
- **Hazard** — **an at-least-once queue feeds a non-idempotent side effect, and nothing at the storage or API layer can tell a redelivery from a new request.**

The timeout is not the cause. Timeouts are normal and will recur. Redelivery is not a bug — it's the delivery guarantee you chose. The hazard is that a charge request carries no stable identity, so "again" and "new" are indistinguishable.

That's also your answer to *why this is the second time*: the previous fix was almost certainly application-level and path-specific too, same as this one.

## The Control-rung device

Three parts, and the middle one is the one people skip:

1. **A deterministic idempotency key derived from the business event** — order ID, invoice ID, event ID. It must be *identical across redeliveries of the same message*. If it's generated at attempt time (`uuid()`), you have built nothing.
2. **Pass it to Stripe as `Idempotency-Key`.** Stripe then returns the original charge instead of creating a second one — this closes the window even when your own DB write never landed, which is the case the local check cannot cover.
3. **`UNIQUE` constraint on the key in your own charges/attempts table, with the intent row inserted *before* the Stripe call.** Attempt 2 gets a constraint violation from the database, not a race. This is the part that makes it a device rather than a convention.

Then make the parameter **required** in the signature, so the next caller can't omit it.

## What should have caught it, and didn't

There is no test that runs the consumer twice on the same message and asserts one charge. Write that one — it's Detection rung, it won't prevent the class, but it proves the constraint fires.

## The sweep — the part worth more than the fix

At-least-once applies to *every* consumer on that queue, so every consumer with a side effect is a live instance of this same hazard, unfixed. I can't enumerate them from here; you should, by shape not by text:

- every consumer on that queue that writes, emails, or calls a third party
- your **Stripe webhook handler** — Stripe redelivers webhooks too, same hazard, opposite direction
- ledger/balance writes (read-modify-write on a balance is the same race in a different costume)
- any retry wrapper that re-invokes a side-effecting function

Report the count. "This hazard is live at 9 other sites" is a different budget conversation than "we fixed the payment worker."

I've written the full retro up at `docs/poka-yoke/retro-2026-08-22-double-charge.md` — let me do that now, but first there's one decision I shouldn't make for you.

---

`★ Insight ─────────────────────────────────────`
The dup-check and the idempotency key look like the same idea, but they sit on opposite sides of the check-then-act boundary. The dup-check *asks* whether work happened; the unique constraint *makes the second attempt unrepresentable*. Anything of the form "query, decide, then act" is racy by construction under concurrency — the only way out is to move the decision into the same atomic operation as the act, which is what a `UNIQUE` insert does.

Stripe's key and your DB constraint are not redundant. Yours fails fast and protects your ledger; Stripe's covers the case where your process dies between the API call and your own write — the exact failure you just had.
`─────────────────────────────────────────────────`

## The decision that's yours

**What is the key derived from?** This is business semantics, not engineering, and getting it wrong reintroduces the bug or blocks legitimate charges:

- **Order/invoice ID** — safest. But: can one order ever be legitimately charged twice (partial capture, retry after genuine card decline, a top-up)? If yes, this key blocks a real charge.
- **Queue message ID** — tempting and usually wrong. Some brokers issue a *new* message ID on redelivery, and a re-enqueue from a different producer path gets a different ID either way. That silently reopens the hole.
- **`(invoice_id, billing_period)` or `(order_id, attempt_reason)`** — right when a legitimate re-charge exists, but you have to be able to name the dimension that distinguishes them.

Tell me which of these matches your billing model — specifically, **is there any case where charging the same order twice is correct?** — and I'll write the retro with a concrete key definition, the migration, and the redelivery test, rather than a placeholder.