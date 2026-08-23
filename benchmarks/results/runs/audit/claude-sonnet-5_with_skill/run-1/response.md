I read `benchmarks/fixtures/payments.ts` (105 lines) and ran it through the three poka-yoke lenses. Worth flagging up front: the file's own header comment says it's an "eval fixture... deliberately hazard-rich" — so if this is actually about to ship as your billing module, make sure you're looking at the right file, not this benchmark asset. Either way, here's what's dangerous about it, ranked by blast radius × how easy the mistake is to make.

## 1. `handleWebhook` — unauthenticated Stripe webhook (line 93)
**Mistake**: anyone who can POST to this endpoint can fabricate an `invoice.paid` event with any `customer` and `amount`.
**Why it bites**: there's no `stripe.webhooks.constructEvent(body, sig, secret)` signature check — `JSON.parse(body)` goes straight into `chargeCustomer`. This isn't just unvalidated input (C7), it's a full auth bypass that triggers real money movement. Anyone can charge an arbitrary Stripe customer on demand.
**Today**: None.
**Device → Control**: verify the Stripe signature header before parsing, reject unverified events, and validate the parsed shape with a schema (zod) instead of trusting `event.data.customer`/`event.data.amount` as `any`.

## 2. `purgeCanceledAccounts` — default arg deletes everything (line 80)
**Mistake**: call it with no argument (the natural way to call a "purge" function) and `cutoff` becomes `new Date()` — i.e. *now*. Every canceled account, regardless of age, matches `canceledAt < now` and gets deleted.
**Why it bites**: this reads like "purge old canceled accounts" but the default makes "old" mean "any age." It's irreversible (F2/F3 combined), and the raw SQL (`$executeRawUnsafe` with string-interpolated date) duplicates the `findMany` filter as a second, separately-maintained source of truth — if they drift, or a new account gets canceled between the two calls (no transaction), the returned count won't match what was actually deleted.
**Today**: None.
**Device → Control**: make `olderThan` required, not optional — force the caller to state the retention window. Wrap both queries in a transaction. Use parameterized SQL, not `$executeRawUnsafe`. Consider a dry-run mode returning the row count before allowing the delete.

## 3. `chargeCustomer` — silent failure + non-idempotent retry (line 37)
**Mistake**: the `catch` swallows every Stripe error and returns `null` on the non-retry path — a declined card, a network blip, and a misconfigured API key all look identical to the caller, and the webhook handler above doesn't even check the return value. Separately, `retry` re-invokes `chargeCustomer` with the *same* customer/amount and **no idempotency key** — if the original charge actually succeeded but the response timed out, the retry charges them again.
**Why it bites**: this is the classic Stripe double-charge shape — matches real incidents where retries without idempotency keys duplicate charges.
**Today**: None (retry flag creates the hazard rather than closing one).
**Device → Control**: require an idempotency key parameter, pass it to `stripe.charges.create({ idempotencyKey })`, and stop swallowing the error — let it propagate or return a typed `Result` the caller must handle.

## 4. `transfer` — non-atomic balance mutation (line 17)
**Mistake**: `from!` and `to!` assume `findUnique` returned a row — a bad account ID crashes instead of failing cleanly. Worse, the two balance updates aren't in a transaction: if the second `update` fails after the first succeeds, money vanishes from one account without landing in the other. No idempotency key either, so a retried transfer double-moves funds.
**Why it bites**: silent partial write on money movement is exactly the kind of bug that surfaces days later during reconciliation.
**Device → Control**: wrap both updates in a DB transaction (or a single conditional update), replace `!` with an explicit not-found check, and add branded `AccountId` types so `transfer(from, to)` can't be called with the args swapped (C1 — they're adjacent same-type params today).

## 5. `updateSubscription` — writes unvalidated status before checking it (line 67)
**Mistake**: `db.subscriptions.update` writes whatever string is passed as `status` *before* the switch even looks at it. The switch has no `default`/`assertNever`, so any status other than `"active"`/`"canceled"` (e.g. `"past_due"`) gets written to the DB with zero side effects run — silently.
**Device → Warning/Control**: make `status` a literal union, validate before the write, and add an exhaustive switch with `assertNever` in the default arm.

**Set aside**: `applyDiscount` has no bounds check on `percentOff` (a value >100 produces a negative price) — real but lower blast radius, worth a one-line clamp/validation when you're in there.

Want me to write this up as `docs/poka-yoke/audit-2026-08-22.md`, or go ahead and apply the fixes for #1 and #2 (the two I'd block shipping on)?