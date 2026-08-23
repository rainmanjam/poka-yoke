Read through it — this is dense with hazards for 105 lines, and worse: several are the exact silent kind that pass review because the code *looks* like normal defensive coding (try/catch, default params, optional args).

## Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-22

**Verdict**: the webhook handler will let anyone with the URL trigger arbitrary charges — that's the one to fix before anything else ships.

### 1. Webhook has no signature verification — Money movement + auth bypass / Trivial
**Where**: `payments.ts:93-100`
**Mistake**: POST any JSON body to the webhook endpoint with `type: "invoice.paid"`.
**Consequence**: `handleWebhook` calls `chargeCustomer` for whatever `customer`/`amount` the request body claims — no check that it came from Stripe. Silent: it looks like a normal event handler, works fine in every test that sends well-formed events.
**Today**: None.
**Device**: verify with `stripe.webhooks.constructEvent(body, sig, endpointSecret)` before touching `event.data`, and reject unsigned/invalid requests → **Control**.
```ts
export async function handleWebhook(rawBody: string, signature: string) {
  const event = stripe.webhooks.constructEvent(rawBody, signature, process.env.STRIPE_WEBHOOK_SECRET!);
  ...
}
```

### 2. `chargeCustomer` retry can double-charge — Money movement / Happens under normal conditions
**Where**: `payments.ts:37-61`
**Mistake**: `stripe.charges.create` times out *after* Stripe already processed it; the caller sees an exception and retries.
**Consequence**: customer charged twice. This isn't hypothetical for this codebase — matches the 340-customer double-charge pattern already on record. Silent: the retried call returns a normal-looking charge object.
**Today**: None — no idempotency key is sent to Stripe at all.
**Device**: pass a stable `idempotencyKey` (e.g. derived from an invoice/order ID) on every `charges.create` call, including the retry → **Control**. Stripe dedupes server-side on that key, so retries become safe by construction instead of by discipline.

Related, smaller issue in the same function: on non-retry failure it swallows the exception and returns `null` (line 59) instead of throwing or logging — a caller that doesn't explicitly check for `null` believes the charge succeeded.

### 3. `transfer` isn't atomic — Money movement / Silent
**Where**: `payments.ts:17-35`
**Mistake**: process crashes, or the second `db.accounts.update` throws, between the debit and the credit.
**Consequence**: money silently vanishes from one account without appearing in the other. Also a TOCTOU: the balance check at line 21 and the update at line 27 aren't in the same transaction, so two concurrent transfers from the same account can both pass the insufficient-funds check and overdraw it.
**Today**: None.
**Device**: wrap both updates (and the read) in a single DB transaction with a `WHERE balance >= amount` guard on the debit, so a concurrent overdraft fails at the DB level instead of in application logic → **Control**.

### 4. `purgeCanceledAccounts` deletes more than it counts, and can purge everything — Irreversible data loss / Easy to misuse
**Where**: `payments.ts:80-91`
**Mistake**: call `purgeCanceledAccounts()` with no argument, expecting "clean up old canceled accounts."
**Consequence**: `olderThan` defaults to `new Date()` — *now* — so every canceled account is deleted, not just old ones. Separately, the raw `DELETE` re-runs its own filter instead of deleting the specific IDs already fetched into `doomed`; if an account transitions to `canceled` between the `findMany` and the `$executeRawUnsafe` call, it gets deleted but isn't in the returned count — the function lies about what it did.
**Today**: None.
**Device**: require `olderThan` (no default), and delete by the exact ID set already fetched (`WHERE id IN (...)`) instead of re-filtering → **Control**. If a truly-optional "purge all" mode is wanted, that should be a separate, loudly-named function, not the default of this one.

### 5. Subscription status switch is non-exhaustive — Silent wrong entitlements / Plausible input
**Where**: `payments.ts:67-78`
**Mistake**: `updateSubscription(id, "past_due")` (or `"trialing"`, `"unpaid"` — real Stripe statuses).
**Consequence**: the DB row updates to the new status, but neither `enableFeatures` nor `disableFeatures` runs. Looks like success — the write succeeded — but entitlements are now out of sync with billing status.
**Today**: None (no `default` case).
**Device**: make `status` a union type instead of `string`, and add a `default` branch that throws on an unhandled value → **Control** (the type system rejects unknown statuses at compile time; the runtime throw catches anything that slips through, e.g. a raw string from a webhook).

### 6. `applyDiscount` has no bound on `percentOff` — Wrong price, silent / Plausible input
**Where**: `payments.ts:63-65`
**Mistake**: call with `percentOff > 100` or `percentOff < 0`.
**Consequence**: negative price (you'd owe the customer) or a price higher than the original, with no error.
**Today**: None.
**Device**: clamp or throw outside `[0, 100]` → **Control**. Cheap fix, easy to miss because the function reads as "obviously correct" arithmetic.

## Set aside
- `from!`/`to!` non-null assertions in `transfer` — if the account doesn't exist this throws rather than corrupting state, so it's a crash (loud), not a silent hazard. Still worth a real "account not found" error for a better message.
- `sendReceipt`/`retry` as adjacent boolean params on `chargeCustomer` — a real footgun at call sites (`chargeCustomer(id, amt, "usd", true, true)` is unreadable), but lower blast radius than the double-charge issue it's attached to. Worth fixing in the same pass since you're already touching that signature.
- Unused `timeout` read from `process.env.WEBHOOK_TIMEOUT` in `handleWebhook` — dead code, likely a stub for replay-window logic that was never wired up.

Want me to write this to `docs/poka-yoke/audit-2026-08-22.md`, or start applying fixes for any of these (I'd start with #1 and #2 — those are the ones that actually move money)?