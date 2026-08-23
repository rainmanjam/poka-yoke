Two things — the second is the actual answer.

**First: this isn't your billing module.** `benchmarks/fixtures/payments.ts` is the eval fixture for this plugin. Its own header says it's deliberately hazard-rich, and its `./db` / `./stripe` imports don't resolve — `fixtures/` contains only `payments.ts` and `documents.ts`. It's the benchmark input, not shipping code, and **fixing it in place would void every benchmark run recorded against it**. So don't ship-block on it; port these findings to the real billing code instead.

(Also: the detector script and the audit-doc write both hit permission prompts, so this is a hand-run of the three lenses, kept in-conversation.)

**Second: the hazards are real shapes, and here's what would bite.** Ranked by blast radius × ease:

1. **`handleWebhook` (`:93`) — no signature verification.** `JSON.parse(body)` feeds `event.data.customer` and `event.data.amount` straight into a charge. Anyone who can reach the URL charges any customer any amount. Worse, it charges on `invoice.paid` — which means *already paid* — so even legitimate deliveries double-charge, and Stripe redelivers on timeout with no idempotency key. `WEBHOOK_TIMEOUT` is read on line 95 and never used: dead config dressed as a control.
2. **`purgeCanceledAccounts()` (`:80`) — no-arg call deletes everything.** `olderThan || new Date()` defaults the cutoff to *now*, so `canceled_at < now` matches every canceled account. The optional param reads as "optional filter"; its default is the most destructive value in range. And the returned count comes from the `findMany`, not the `DELETE` — a plausible wrong number, which beats no number for danger.
3. **`transfer` (`:17`) — destroys money on a bad destination id.** The debit at `:25` commits, then `to!.balance` at `:31` throws on `undefined`. Source charged, destination never credited, no rollback. The `!` assertions are what let that compile. Same function has a read-modify-write race that lets two concurrent transfers conjure money.
4. **`chargeCustomer` (`:44`) — `retry` + `catch { return null }`.** A timeout is indistinguishable from a decline, and the charge may already have succeeded — so the retry charges again, and the `null` erases which happened. This is the 340-customer incident shape exactly.
5. **`updateSubscription(id, "cancelled")` (`:67`)** — British spelling writes to the DB, falls through a `default`-less switch, customer stays canceled *and* keeps paid features. Silent.

Plus: `applyDiscount(price, percentOff)` takes two swappable unbounded numbers (`applyDiscount(20, 100)` → 0); `chargeCustomer`'s five positional params end in two adjacent booleans; `void sendReceiptEmail` drops rejections silently.

★ Insight ─────────────────────────────────────
Findings 1, 2 and 4 share one root: **an optional thing whose default is the dangerous value.** Optional cutoff → delete-all. Absent idempotency key → replay charges. Absent signature → trust anything. The device is the same each time — make it a required parameter, so forgetting it fails at the call site rather than at 4pm on a Friday.
─────────────────────────────────────────────────

Want me to write the full audit (all 8, with device sketches and rungs) to `docs/poka-yoke/audit-2026-08-22.md`? I'll need the write approved. And if there's a real billing module outside this repo, point me at it — that's where the devices belong.