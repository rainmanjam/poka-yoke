File write wasn't permitted, so here's the audit inline. Ranked by blast radius × ease of mistake.

## Ship-blockers

**1. `handleWebhook` (line 93) — unauthenticated money movement.** No `stripe.webhooks.constructEvent`, so `event.data.customer` and `event.data.amount` are attacker-controlled and flow straight into `chargeCustomer`. Anyone who can POST mints charges. Also: `JSON.parse` on untrusted input throws uncaught; `WEBHOOK_TIMEOUT` is read and never used; and `invoice.paid` *triggering a charge* is backwards — the invoice was already paid. **Device:** verify signature → schema-parse → dedupe on `event.id`.

**2. `transfer` (line 17) — debits before it knows the destination exists.** Line 25 debits; line 31 dereferences `to!`, which is `null` for a bad id, and throws. No transaction, so the money is gone and the error reads as a null-property bug. Four more hazards stacked: check-then-act race between the balance read (18) and write (27) — same TOCTOU shape as your double-charge incident; `fromAccount`/`toAccount` adjacent same-typed strings, so `transfer(dst, src, amt)` compiles and runs; `!` asserting DB rows exist; `Account.currency` declared and never compared. **Device:** one `$transaction`, `updateMany` with `where: { balance: { gte: amount } }` so the guard *is* the write, options object + branded `AccountId`, `findUniqueOrThrow`.

**3. `chargeCustomer` (line 37) — `catch { return null }` collapses "declined" and "timed out after the card was charged" into one falsy value.** A caller reading `if (!charge) retry()` re-charges. The `retry` param has no idempotency key, so on a Stripe timeout the second charge is guaranteed, not possible. Plus two adjacent positional booleans and a `void`-silenced floating promise. **Device:** required `idempotencyKey` field (a caller who hasn't thought about identity can't compile), options object, let it throw.

## Also real

**4. `purgeCanceledAccounts()` (line 80)** — `olderThan || new Date()` means calling it with *no arguments* deletes every canceled account. The least typing gets the most destructive value. The returned count comes from a separate `findMany`, so it under-reports. **Device:** required cutoff, `maxRows`, single `deleteMany` returning the real count.

**5. `updateSubscription` (line 67)** — `status: string` writes `"cancelled"` to the DB happily, then the switch falls through with no `default`. Row says canceled, features stay on, nothing logs. **Device:** union type + `never` exhaustiveness, in a transaction.

**6. `applyDiscount` (line 63)** — `applyDiscount(30, 1000)` returns `-270`. Unclamped percent, float money, returns a non-integer into Stripe's integer `amount`.

**7. Units are ambiguous** — `balance: number` vs `amountCents`. Mixing them is a silent 100×.

`★ Insight ─────────────────────────────────────`
Findings 2 and 3 are the same root shape as the incident in your history: a gap between deciding and acting. The fix pattern is identical — move the check *into* the write (a `WHERE` clause, a unique constraint) so there's no window to interleave.
`─────────────────────────────────────────────────`

**One decision I can't make for you** — it's the same one that blocked you before: what does the idempotency key scope to? Order ID means a retried order is safe but a legitimate re-charge is blocked. `(order, attempt)` allows deliberate retries but reopens redelivery. Your call; it shapes the signature in finding 3.

Want me to write the full version to `docs/poka-yoke/audit-2026-08-22-payments.md`? It needs write permission.