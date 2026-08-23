Writing the report file needs approval too, so here it is in the conversation instead.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-22

**Verdict**: `handleWebhook` parses an unverified body and charges a customer from it. Anyone who can reach that endpoint can move money. Everything else waits.

### 1. Forged webhook moves money — money + auth bypass / trivial · `payments.ts:93`
No signature check, `JSON.parse` into `any`. The `customer` and `amount` you POST are the ones charged, and it looks like ordinary webhook traffic in the logs.
**Today**: None → **Device**: `stripe.webhooks.constructEvent(rawBody, sig, secret)` *then* a zod discriminated union over the event types you handle, so an unverified payload has no representation. **Control.** The handler has to take the raw `Buffer` — a body-parser that already ran defeats it.

### 2. `purgeCanceledAccounts()` with no argument deletes everything — irreversible / requires only forgetting · `:80`
`olderThan || new Date()` makes the omitted case *now* — the widest possible cutoff. F3 feeding F2: an optional parameter defaulting to its most destructive value.
**Today**: None → **Device**: required cutoff, `maxRows` cap that throws above it, and delete by the IDs you counted. **Control.**
Three hazards stacked: `$executeRawUnsafe` duplicates the predicate in a second dialect (`canceledAt` / `canceled_at`) where the copies can drift silently, and `doomed.length` comes from a *different* query than the delete — so the number you log is not the number of rows removed.

### 3. Negative amount reverses `transfer` and walks past the balance check — money / silent · `:17`
`transfer(mine, theirs, -100)`: `from.balance < -100` is false, so the guard passes, then `balance - (-100)` credits the caller and debits the other account. Money out of a sign, and reconciliation sees a well-formed transfer.
**Today**: None → **Device**: `PositiveCents` brand whose constructor rejects `<= 0`. **Control.** A runtime `if (amount <= 0) throw` is **Warning** — it protects this one function; the next money-mover starts from zero.

### 4. Retry without an idempotency key double-charges — money / silent · `:56`
A timeout *after* Stripe accepted the charge lands in `catch`, and the retry creates a second one. M2 exactly — and finding 1's redelivery path re-enters the same charge with no dedupe.
**Today**: None → **Device**: **required** `idempotencyKey` parameter + unique index on `(customer_id, idempotency_key)`. **Control.** Necessary, not sufficient: reserve the key in the same transaction as the effect, bind it to the payload so a reused key with different arguments errors instead of silently no-op'ing, and replay the stored result. A retry that gets a constraint violation has learned nothing about whether the first attempt worked.

### 5. `catch` returns `null` — silent wrong state · `:59`
Declined, network-failed, and succeeded are indistinguishable. `:98` discards the result entirely, so the webhook returns 200 for a charge that never happened and the provider never redelivers.
**Today**: None → **Device**: `{ ok: true; charge } | { ok: false; reason; error }` the caller must narrow. **Control.**

### 6. Stringly-typed status leaves canceled customers with paid features — silent revenue loss / one typo · `:67`
`"cancelled"` writes fine, matches no `case`, `disableFeatures` never runs. C4 + F1 compounding — no default arm either, so a new `past_due` variant silently does nothing everywhere.
**Today**: None → **Device**: literal union + `default: assertNever(status)`. **Control**, one line per switch.

### 7. `transfer(from, to)` — adjacent strings, swap compiles — money / silent · `:17`
**Device**: branding `AccountId` does *not* fix this — both params stay `AccountId`. Control needs distinct `SourceAccount`/`DestinationAccount` types; an options object `transfer({ from, to, amount })` is **Warning** (makes the swap visible, not impossible) but costs one line, and it's what I'd take.

### 8. Two writes, no transaction, over a check-then-act race — silent corruption · `:21-32`
Concurrent transfers both read the same balance and both pass the guard (M5); or the debit commits and the credit throws and the money is gone (F5). The `to!` assertion makes that second case reachable from a typo'd account ID — the debit at `:25` has already committed when `:29` throws.
**Device**: one `$transaction`, debit as a conditional update — `where: { id: from, balance: { gte: amount } }`, then assert `count === 1`. The guard becomes the write's own predicate, so it can't race. **Control.**

### 9. `applyDiscount(20, 100)` vs `(100, 20)` — silent · `:63`
Swap returns 0 instead of 80; an unbounded `percentOff` of 150 returns a negative price that becomes a credit downstream. **Device**: `Percentage` parsed to 0–100, `Money` for price. **Control.**

### 10. Currency is decorative — silent corruption · `:13, :17, :40`
`transfer` never reads `Account.currency`, so 100 USD arrives as 100 EUR. `chargeCustomer` defaults `currency = "usd"` (F3), so forgetting it charges the wrong denomination confidently. **Device**: `Money { cents, currency }` with mixed-currency arithmetic failing to typecheck. **Control.**

**Set aside (5)**: `void sendReceiptEmail` (M6 — covered by `no-floating-promises` as error); `WEBHOOK_TIMEOUT` read but never used or validated (F4 in waiting); `balance: number` (C6, folded into 3 and 10); `Account.status: string` (same shape as 6); `ownerId` never consulted by `transfer` — no authorization check at all, which on real code would outrank most of this list and belongs to `authz`.

`★ Insight ─────────────────────────────────────`
- Findings 1–4 are all the same structural failure: **money movement with no admission control at the boundary**. Fixing them one function at a time is why the shapes recur — the durable version is one parsed, branded boundary type (`Money`, `IdempotencyKey`, verified `Event`) that all four paths must pass through.
- The ranking deliberately puts finding 8's *silent* corruption above findings that crash. A `to!` TypeError pages you; a lost credit reconciles wrong three weeks later.
- Note how often the hazard is the **default**, not the code: `olderThan?`, `currency = "usd"`, `retry = false`. Defaults are where a decision goes to hide.
`─────────────────────────────────────────────────`

Two things I need from you before applying any of this:

**The idempotency-key scope decision** — this is the same one that blocked the double-charge work earlier today, and finding 4 can't be implemented without it. Is the key scoped per `(customer, invoice)`, per request from the caller, or derived from the Stripe event ID? Each gives different behavior on legitimate repeat charges for the same invoice.

**Finding 7's device** — distinct `SourceAccount`/`DestinationAccount` types reach Control but add vocabulary every caller has to learn; the options object is Warning but free. Your call which is worth it.

I haven't edited anything — per the skill, devices that reshape interfaces get proposed first. Say which findings you want applied and I'll do them with `poka-yoke:` marker comments naming the mistake each one blocks. Bash and Write both need approval in this session, so you'll need to grant those (or run in an interactive one) before I can apply changes or run the detector's mechanical pass.