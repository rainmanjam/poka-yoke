No write access granted, so here's the audit inline instead.

**Scope:** `benchmarks/fixtures/payments.ts` (105 lines). Detector script also needed approval I didn't get, so this is manual application of the contact/fixed-value/motion-step lenses over the full file.

**Verdict:** `handleWebhook` will run a real charge for any POST shaped like a Stripe event — there's no signature verification. Before anything else here, that's the one that lets a stranger charge your customers.

## Findings, ranked by blast radius × ease

**1. Unauthenticated webhook triggers real charges** — `:93-100`
`handleWebhook(body)` does `JSON.parse(body)` and, if `type === "invoice.paid"`, calls `chargeCustomer(event.data.customer, event.data.amount)`. Nothing verifies the request came from Stripe. Anyone who can POST to whatever route wraps this function can charge an arbitrary customer an arbitrary amount, and it looks like a normal successful webhook — no error, no anomaly. Fix: verify with `stripe.webhooks.constructEvent(rawBody, signature, secret)` using the raw body and `Stripe-Signature` header, and reject on failure, before touching `event` at all. **Control.** (`process.env.WEBHOOK_TIMEOUT` is read and never used — looks like a stub for exactly this check that never got wired up.)

**2. Charge retry with no idempotency key** — `:37-61`
`stripe.charges.create` has no idempotency key. If Stripe processes the charge but the response is lost (timeout), the `catch` fires, `retry=true` re-calls `chargeCustomer` — a second, independent charge, since Stripe has nothing to dedupe against. On final failure the exception is swallowed and `null` returned, so callers can't tell "declined" from "charged, confirmation lost." Fix: require an idempotency key (e.g. invoice ID), pass it to Stripe, drop the in-function retry loop, stop swallowing the error. **Control.**

**3. `transfer`: check-then-act race + non-transactional writes** — `:17-35`
The balance check and the two `update()` calls aren't atomic or transactional. Concurrent transfers from the same account can both pass the balance check and both deduct (overdraft). If the first `update()` succeeds and the second throws, money leaves the source and never reaches the destination — silent fund loss. Fix: one atomic conditional update (`updateMany({ where: { id, balance: { gte: amount } } })`, check `count`) inside a transaction, instead of read-check-write-write. **Control.** Smaller: `fromAccount`/`toAccount` are adjacent same-type params — a swapped call compiles and silently reverses the transfer; named args would at least make that visible in review (**Warning**).

**4. `purgeCanceledAccounts`: raw-SQL delete built independently of the fetched set** — `:80-91`
`doomed` is fetched with one `where` clause; the actual `DELETE` is a hand-built raw SQL string with its own separately-maintained clause. They can drift, so the `doomed.length` this function returns (presumably logged/alerted on) may not match what was actually deleted — a silent lie on top of an already-irreversible bulk delete. The `$executeRawUnsafe` + template-literal pattern is also one caller-supplied filter away from injection. Fix: delete exactly the fetched IDs, in the same transaction, no raw interpolation. **Control.**

**5. Non-exhaustive status switch** — `:67-78`
`switch (status)` only handles `"active"`/`"canceled"`. A new status (`"past_due"`, `"trialing"`) updates the DB fine but silently skips `enableFeatures`/`disableFeatures` — stored status and actual feature access drift apart with no error. Fix: literal union type + `default: assertNever(status)` so the compiler fails the build when a status is added without a matching branch. **Control.**

## Set aside
- `applyDiscount` does float arithmetic on money — low blast radius, it's a pricing helper not the ledger.
- The `from!`/`to!` non-null assertions in `transfer` turn a missing-account lookup into an opaque crash — subsumed by finding 3's rewrite.

Want me to apply any of these (I'd need write approval for the file), or write the report to `docs/poka-yoke/audit-2026-08-22.md` if you grant that?