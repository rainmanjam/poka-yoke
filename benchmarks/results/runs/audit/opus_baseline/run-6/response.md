Write access was denied, so here it is in the conversation instead.

**First, the thing you should know before anything else:** this isn't a shippable billing module. Line 3 of the file says *"Deliberately hazard-rich, in ways that look like ordinary working code rather than like a quiz,"* and `benchmarks/scenarios.json` is the only place that references it — it's the input fixture for your benchmark harness. So "been through review already" is true in a sense you may not have meant: the hazards *are* the fixture. **Don't let anyone fix this file** — patching it invalidates every baseline under `benchmarks/results/`.

The audit is still worth having (it's the answer key, and these shapes get copied into real modules), so here it is. One caveat: `detect_hazards.py` was denied too, so everything below is from reading, not the detector.

---

## What would actually bite you

**1. `handleWebhook` (line 93) — unsigned, unvalidated, moves money.** No signature check, `JSON.parse` into `any`, and `event.data.customer`/`event.data.amount` go straight into a charge. Anyone who can reach the endpoint bills any customer any amount. No attacker required either: Stripe redelivers on timeout, and there's no event-ID replay guard. Also `const timeout = process.env.WEBHOOK_TIMEOUT` is read and never used — dead config that reads like an enforced timeout. And charging *on* `invoice.paid` is inverted; that event announces money already collected.

**2. `transfer` (line 17) — three separate ways to destroy money.**
- Negative `amount`: `from.balance < -1000` is false, guard passes, the debit *adds* and the credit *subtracts*. Unauthorized withdrawal from any account.
- Unknown `toAccount`: `from!` resolves, check passes, **the debit commits**, then `to!.balance` throws on null. No transaction, no rollback. Money gone.
- Two concurrent transfers read the same balance and both write `balance - amount`. Lost update.

Plus: currency is never compared (USD into EUR just adds), and `balance: number` is a float.

**3. `chargeCustomer` (line 55) — `catch { return null }`, and `retry` double-charges.** Every caller here ignores the return value. Worse, `retry` re-issues on *any* throw, including a request that succeeded at Stripe but whose response never arrived. No idempotency key. That's the exact 340-customer shape already in this repo's history.

**4. `purgeCanceledAccounts()` (line 80) — the default argument is the maximally destructive value.** `olderThan || new Date()` means calling it bare sets the cutoff to *now* and deletes every canceled account ever. Hard delete, no limit, no dry run. It also returns `doomed.length` from a *different* query than the one that deleted — a count that can't be wrong because it isn't measuring anything.

**5. `updateSubscription` (line 67) — typo `"cancelled"` with two Ls.** Writes to the DB fine, switch has no `default`, falls through silently. Subscription reads canceled, `disableFeatures` never runs, customer keeps paid features for free. Nothing reports it.

**6. Swappable arguments everywhere.** `transfer(to, from, amt)` moves money backwards and returns a receipt that looks right. `applyDiscount(10, 5000)` — and `percentOff` is unbounded, so `150` produces a negative price (a credit) and `0.5` meaning "half off" gives 0.5%. `chargeCustomer(c, 500, "usd", false, true)` reads as nothing at the call site.

**7. `void sendReceiptEmail(...)` (line 52)** — floating promise, unhandled rejection, receipt silently lost.

---

`★ Insight ─────────────────────────────────────`
Notice the ranking: the null-returning `catch` outranks anything that crashes. A charge that throws wakes someone up; a charge that returns `null` into a discarded variable is revenue that never existed. Same for `purgeCanceledAccounts` returning a count from a query that didn't do the deleting — a number that *cannot* be wrong because it isn't measuring the thing it's reported as. That's the same failure your CLAUDE.md warns about in the detector itself: a check that can't go red.

The other pattern worth naming: in `transfer`, `from!` and `to!` aren't equally bad. `from!` throws before any write. `to!` throws *after* the debit committed. Identical syntax, and only one of them destroys money — position relative to the write is what matters, not the assertion.
`─────────────────────────────────────────────────`

---

Where I'd like your input, since this touches a decision your notes say is still open — the idempotency-key **scope** for `chargeCustomer`. The device is one line, but the key's identity determines the semantics:

- `charge:${orderId}` — one charge per order, ever. Safe against redelivery, but blocks a legitimate second charge on the same order (a top-up, a corrected amount).
- `charge:${orderId}:${attemptId}` — dedupes only within a retry loop. Permits deliberate re-charges, but a queue redelivery that generates a fresh `attemptId` sails right through — which is how the 340-customer incident happened.
- `charge:${invoiceId}` — matches Stripe's own billing grain, but only exists if you're invoice-driven.

Your domain knowledge decides this one; I'd rather not guess. Which grain is a "second charge for the same thing" in your billing model?

And say the word if you want me to write the full report to `docs/poka-yoke/audit-2026-08-22-payments-fixture.md` — I'll need write permission for that path.