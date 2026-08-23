Write needs approval too, so here's the report inline.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-21

**Scope**: one file, 105 lines, read in full (detector couldn't run — needed approval).
**Verdict**: `purgeCanceledAccounts()` with no argument deletes every canceled account that exists via raw SQL, with nothing in its way. Fix that, then make `chargeCustomer` unable to double-charge.

**First, the elephant**: the file header (`payments.ts:1-4`) says *"eval fixture… deliberately hazard-rich… every hazard here passes review."* It lives under `benchmarks/fixtures/`. Either it's the benchmark fixture and shouldn't ship at all, or a fixture got promoted to production. Your nervousness is justified either way.

## Findings (blast radius × ease)

**1. Purge with no cutoff = delete everything** — `payments.ts:80-88`
Mistake: call `purgeCanceledAccounts()` with no arg (or `undefined` from unset config). `olderThan || new Date()` makes "no cutoff" mean "now" → every canceled account ever, raw interpolated SQL, no transaction, returns a happy count. Silent.
Today: None → Device: required `{ canceledBefore, dryRun }` object, reject cutoffs inside the retention window, `deleteMany` instead of `$executeRawUnsafe`. **Control.**

**2. Retry double-charges** — `payments.ts:44-60`
Stripe succeeds, response times out, `retry` fires again → two charges. And the `catch` returns `null`, so callers retry *on top of that*. Silent — returns a valid charge object.
Today: None → Device: mandatory `idempotencyKey` passed to Stripe; remove the catch. **Control.**

**3. Webhook charges from an unverified body** — `payments.ts:93-99`
Anyone who can reach the URL POSTs `{"type":"invoice.paid",...}` and charges any customer any amount; replays charge twice. Also: it creates a *new charge* in response to "invoice *paid*", so even legit events double-bill.
Today: None → Device: `stripe.webhooks.constructEvent` before parsing, unique-keyed `event.id` table, and don't charge on "paid". **Control.**

**4. `transfer(from, to, amount)` — swappable, self-transfer, negative** — `:17`
Reversed args, `transfer(a, a, n)`, or negative amount (passes the balance check, moves money backwards). All return success. Silent.
Device: single typed arg, branded `AccountId`, positive `Money`, reject `from === to`. **Control.**

**5. Transfer isn't atomic** — `:18-32`
Two reads, a stale balance check (TOCTOU), two separate writes. Concurrent transfers overdraft; a crash between writes vanishes money.
Device: one `$transaction` with `decrement`/`increment` + `where: { balance: { gte: amount } }`, plus DB `CHECK (balance >= 0)`. **Control.**

**6. Cross-currency transfer** — `:9-15`
`currency` is a free string never compared: 100 USD → 100 JPY. Silent.
Device: `Money { cents, currency }`, throw on mismatch. **Control.**

**7. `applyDiscount(price, 0.2)`** — `:63` — 0.2% off instead of 20%; `120` gives negative prices. Branded `Percent` (0–100). **Control.**

**8. `updateSubscription(id, "cancelled")`** — `:67-78` — typo'd/unknown status updates the row, falls through the switch, features stay enabled forever. Union type + exhaustive switch. **Control.**

**9. `return null` hides every failure** — `:59` — order marked paid, no charge, error gone. Covered by #2.

**10. Five positional params, three bool/defaults** — `:37-43` — `chargeCustomer(id, 500, "eur", false)` silently flips the wrong flag. Covered by #2's options object.

**Set aside**: `from!`/`to!` assertions (loud crash, fine); unused `WEBHOOK_TIMEOUT`; fire-and-forget receipt email; `status: string` on `Account` (same fix as #8).

★ Insight ─────────────────────────────────────
- Nothing here is a *bug* — every function works when called correctly. That's why it passed review. Poka-yoke asks a different question: what can a tired caller do *wrong* without anything stopping them?
- Eight of ten findings are the same device in different clothes: replace a primitive (`string`, `number`, positional bool) with a type that can't hold the wrong value. The signature becomes the reviewer.
─────────────────────────────────────────────────

**Recap**: 10 findings, all currently at "None" — no device stands between a caller and the mistake. Top three (purge, double-charge, unverified webhook) are money-moving and silent. Per the audit skill I haven't edited anything; say which you want applied and I'll do them (the file write and detector run will need permission approval).