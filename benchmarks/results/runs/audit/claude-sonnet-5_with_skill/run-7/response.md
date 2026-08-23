One important thing before the findings: this file's own header says it's a **deliberately hazard-rich eval fixture** for the benchmark suite ("Every hazard here is one that ships in real codebases and passes review"), not committed billing code — `git log` shows it landed via "Replace ad-hoc benchmarks with one comprehensive reproducible suite" and there's no pending diff on it. If you meant a different `payments.ts`, point me at it. Otherwise, the hazards below are real regardless of intent, and a couple of them echo the double-charge incident from earlier today (queue redelivery / Stripe timeout, 340 customers) closely enough that they're worth treating seriously either way.

**Scope**: `benchmarks/fixtures/payments.ts`, 105 lines, single file, no uncommitted diff.

# Poka-Yoke Audit — payments.ts — 2026-08-22

**Verdict**: `handleWebhook` will double-charge or accept forged charge requests, and `chargeCustomer`'s retry path can independently double-charge — this is the same failure shape as this morning's 340-customer incident, reproduced in miniature.

## Findings

### 1. Webhook has no signature verification and no event dedup — Money movement + auth bypass / Silent
**Where**: `payments.ts:93-100`
**Mistake**: Anyone who can POST to this endpoint can submit `{type: "invoice.paid", data: {customer, amount}}` and trigger a real Stripe charge against any customer ID they name — there's no `stripe.webhooks.constructEvent` / signature check. Separately, Stripe's documented at-least-once delivery means the *same* legitimate event can arrive twice, and nothing keys off `event.id` to skip a repeat.
**Consequence**: Forged or duplicate charge attempts, silently — `chargeCustomer`'s own catch (finding 2) swallows the failure either way, so nothing surfaces.
**Today**: None.
**Device**: Verify the Stripe signature before parsing (`stripe.webhooks.constructEvent(body, sig, secret)` — rejects the request if it fails) → **Control**. Record `event.id` with a unique constraint before processing, so a redelivered event is a no-op rather than a second charge → **Control**.

### 2. `chargeCustomer` retries without an idempotency key, and swallows the failure — Money movement / Silent
**Where**: `payments.ts:37-61`
**Mistake**: On any Stripe error (including a timeout where the charge actually succeeded), the function retries the *exact same charge* with no idempotency key, then on final failure returns `null` instead of throwing.
**Consequence**: Timeout-triggered retries double-charge the customer — this is the precise mechanism from this morning's incident. And because failure returns `null` silently, `handleWebhook` (which never checks the return value) treats a failed charge as handled.
**Today**: None — `retry` is a boolean flag (also a C2 hazard: unreadable call site, and a decision hidden behind a default per F3), not a real retry-safety mechanism.
**Device**: Required `idempotencyKey: IdempotencyKey` parameter, passed to Stripe's own `idempotencyKey` request option, backed by your own dedup if you store charges → **Control**. Let the error propagate (or return a typed `Result`) instead of `null` → **Control** (makes "did it work" a value the caller must handle, not a value they can ignore).
```ts
async function chargeCustomer(
  customerId: CustomerId,
  amountCents: Cents,
  idempotencyKey: IdempotencyKey,
  currency: Currency,
): Promise<Charge> {
  return stripe.charges.create(
    { customer: customerId, amount: amountCents, currency },
    { idempotencyKey },
  ); // let it throw — caller decides retry policy, keyed on the same idempotencyKey
}
```

### 3. `transfer` has no transaction, no currency check, and a check-then-act race — Money movement / Silent
**Where**: `payments.ts:17-35`
**Mistake**: Balance is checked, then two independent `update` calls run outside any transaction. Two concurrent transfers from the same account can both pass the balance check before either write lands (M5), overdrawing the account. If the process dies between the debit and the credit, money vanishes from the system with no record (F5). Nothing checks `from.currency === to.currency`, so a transfer between a USD and EUR account just adds/subtracts the raw number as if they were the same unit.
**Consequence**: Silent overdraft under concurrency, silent money loss on crash, silent currency mismatch — none of these throw.
**Today**: None.
**Device**: Wrap both updates in a DB transaction with a conditional update (`WHERE balance >= amount`) instead of read-then-write, so the debit is atomic and a concurrent race fails the second writer instead of both succeeding → **Control**. Reject when `from.currency !== to.currency` → **Control**, cheap.

### 4. `purgeCanceledAccounts` defaults its cutoff to *now*, and deletes via a separate raw query from the one it counted — Irreversible data loss / Silent-plausible
**Where**: `payments.ts:80-91`
**Mistake**: Call `purgeCanceledAccounts()` with no argument (easy to do — it's optional) and `cutoff` becomes "this instant," so the delete matches *every* canceled account regardless of age, not just old ones (F3: a default with no safe value). Separately, the returned count comes from a `findMany` that ran *before* the raw `DELETE`, so if any account is canceled in between, the function reports a different number than it actually deleted (M5 race) — and the delete itself is built by string-interpolating a date into `$executeRawUnsafe`, an unparameterized query for no reason (F6-adjacent, needlessly bypasses the query builder that would parameterize it).
**Consequence**: A caller who forgot the argument, expecting "purge stale ones," wipes every canceled account — irreversible — and the return value lies about how many.
**Today**: None.
**Device**: Make `olderThan: Date` required (no default) → **Control**. Use the query builder's `deleteMany` with the same `where` used for the count, so the number returned is the number affected → **Control**. Drop `$executeRawUnsafe` entirely; nothing here needs raw SQL.

### 5. `updateSubscription` writes `status` before validating it, and the switch silently no-ops on anything else — Silent data corruption
**Where**: `payments.ts:67-78`
**Mistake**: The DB write happens unconditionally on line 68, for any string. The switch only handles `"active"`/`"canceled"`; any other value (`"past_due"`, a typo, a new status added elsewhere) writes to the DB successfully but silently skips enabling/disabling features (F1: no default/`assertNever`).
**Consequence**: Stored status and actual feature access drift apart with no error anywhere in the stack.
**Today**: None.
**Device**: A `SubscriptionStatus` literal union validated before the write, and an `assertNever` default arm so a new status fails to compile until every switch handling it is updated → **Control**.

## Set aside
- `applyDiscount` — no bounds check on `percentOff` (>100 goes negative, negative goes up) — real, but low blast radius on its own; fix alongside finding 3 if you're touching money types anyway.
- `transfer(fromAccount, toAccount)` as adjacent same-type string params (C1, swappable at the call site) — subsumed by finding 3's transaction rewrite; brand `AccountId` while you're in there.
- `balance`/`amount` as `number` (C6, money-as-float) — cross-cutting through the whole file; worth a `Money`/cents type as a follow-up, not its own PR.
- Unused `process.env.WEBHOOK_TIMEOUT` read in `handleWebhook` — dead code, not a hazard.

Want me to write this to `docs/poka-yoke/audit-2026-08-22.md`, or leave it here? And say the word if you want me to apply any of the five devices — I'll hold off editing until you do.