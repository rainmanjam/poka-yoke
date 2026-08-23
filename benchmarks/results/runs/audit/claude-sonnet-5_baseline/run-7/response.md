Read the whole file (105 lines, small enough to review directly). The hazard detector needs Bash approval that didn't come through — I went with manual review across the three lenses instead, which is sufficient for a file this size. Here's what I found, ranked by blast radius × ease of mistake.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-22

**Scope**: single file, 105 lines, manual review (detector run was blocked by pending Bash approval)
**Verdict**: `handleWebhook` will process a fake or replayed Stripe event and charge real money with no way to tell — that's the one to fix before anything else ships.

## Findings

### 1. Webhook handler trusts unverified, unbounded input — Money movement + auth bypass / Trivial
**Where**: `benchmarks/fixtures/payments.ts:93-100`
**Mistake**: Anyone who can reach this endpoint POSTs `{"type":"invoice.paid","data":{"customer":"cus_victim","amount":999999}}` — no Stripe signature check exists, so nothing distinguishes a real event from a forged one. Separately, Stripe legitimately redelivers the same event on timeout, and there's no idempotency tracking, so a genuine retry double-charges.
**Consequence**: Arbitrary charges to arbitrary customers, or duplicate charges on retry. Silent — it returns 200-shaped success either way, nothing logs a rejection.
**Today**: None.
**Device**: Verify `stripe.webhooks.constructEvent(body, signature, secret)` before touching `event.data`, and record `event.id` in a unique-constrained `processed_webhook_events` table before acting — a second delivery of the same `event.id` becomes a no-op, not a second charge. → **Control**

```ts
export async function handleWebhook(rawBody: string, signature: string) {
  const event = stripe.webhooks.constructEvent(rawBody, signature, process.env.STRIPE_WEBHOOK_SECRET!);
  const inserted = await db.processedWebhookEvents.createIfNotExists({ id: event.id }); // poka-yoke: rejects a replayed event id [control]
  if (!inserted) return;
  if (event.type === "invoice.paid") {
    await chargeCustomer(event.data.customer, event.data.amount);
  }
}
```
(The unused `timeout` env read on line 95 is a leftover — worth deleting or wiring in, but it's noise next to the two hazards above.)

### 2. `transfer(fromAccount, toAccount, amount)` — swappable accounts, non-atomic, unvalidated amount — Money movement, silent / Easy typo
**Where**: `benchmarks/fixtures/payments.ts:17-35`
**Mistake**: `fromAccount` and `toAccount` are adjacent same-typed strings — a caller swaps them (`transfer(payeeId, payerId, amt)`) and money silently flows backward with no type error. Separately, `amount` isn't checked for being positive/finite, so `transfer(a, b, -500)` runs the balance check backwards and effectively transfers *into* `a`. And the two `update` calls aren't in a transaction, so a crash between them leaves money debited from one account and never credited to the other.
**Consequence**: Wrong-direction transfers, negative-amount reversals, and partial transfers on crash — all silent, all look like a normal successful call.
**Today**: None (the `from!`/`to!` non-null assertions mean a bad ID just throws a cryptic `TypeError` instead of a clean error, which isn't a device — it's an accident).
**Device**: Branded IDs so `fromAccount`/`toAccount` can't be positional-swapped without a compile error, assert `amount > 0`, and wrap both updates in one DB transaction. → **Control** for the type confusion and validation; the transaction closes the crash-consistency gap.

```ts
type AccountId = string & { readonly __brand: "AccountId" };

export async function transfer(from: { account: AccountId }, to: { account: AccountId }, amountCents: number) {
  if (!Number.isInteger(amountCents) || amountCents <= 0) throw new Error("amount must be a positive integer");
  return db.$transaction(async (tx) => { /* both updates here */ });
}
```

### 3. `chargeCustomer` retries without an idempotency key and swallows the original error — Money movement, silent / Automatic (no user action needed)
**Where**: `benchmarks/fixtures/payments.ts:37-61`
**Mistake**: On a network timeout, Stripe may have already created the charge even though the client saw an error. `retry=true` calls `chargeCustomer` again with no `idempotencyKey` on `stripe.charges.create`, so Stripe treats it as a brand-new charge — two charges for one purchase. If the retry also fails, the function `return null`s, discarding the actual error entirely.
**Consequence**: Duplicate charge on retry (silent — caller gets back a `charge` object indistinguishable from a first-time success). On terminal failure, the caller gets `null` and has to guess why.
**Today**: None.
**Device**: Pass a caller-supplied or order-derived `idempotencyKey` through to Stripe so retries collapse to the same charge, and return a discriminated result instead of `null` so failure can't be mistaken for "nothing happened."

```ts
const charge = await stripe.charges.create(
  { customer: customerId, amount: amountCents, currency },
  { idempotencyKey },     // poka-yoke: collapses a retried charge onto the original [control]
);
// ...
} catch (e) {
  if (retry) return chargeCustomer(customerId, amountCents, currency, sendReceipt, false, idempotencyKey);
  return { ok: false, error: e } as const;   // instead of null
}
```
This is the exact shape of the double-charge incident already in your notes for this branch — worth treating as the same class of bug, not a new one.

### 4. `purgeCanceledAccounts` — raw SQL string interpolation, no grace period, delete set not tied to the queried set — Irreversible data loss / Trivial (default args alone are dangerous)
**Where**: `benchmarks/fixtures/payments.ts:80-91`
**Mistake**: `$executeRawUnsafe` interpolates `cutoff.toISOString()` directly into SQL — if `cutoff` is ever derived from anything less trusted than "now," it's a SQL injection vector, and using the `Unsafe` variant for a value that could be parameterized is itself the affordance. Calling `purgeCanceledAccounts()` with no argument deletes every account canceled up to *this instant* — no grace period, no dry run. And the `DELETE` re-derives its own row set from raw SQL instead of deleting the IDs already fetched into `doomed`, so the count returned isn't provably the count deleted if anything changes between the two queries.
**Consequence**: Permanent, unrecoverable loss of billing accounts, silently larger than intended if called without thinking about the default.
**Today**: None.
**Device**: Parameterize the query, require an explicit cutoff (no default), and delete by the exact ID set already fetched.

```ts
export async function purgeCanceledAccounts(olderThan: Date) {           // no default — forces the caller to decide
  const doomed = await db.accounts.findMany({ where: { status: "canceled", canceledAt: { lt: olderThan } } });
  await db.accounts.deleteMany({ where: { id: { in: doomed.map(a => a.id) } } }); // poka-yoke: deletes exactly what was shown, nothing found later [control]
  return doomed.length;
}
```

### 5. `updateSubscription` switch is non-exhaustive — Silent wrong state / Any typo or new status value
**Where**: `benchmarks/fixtures/payments.ts:67-78`
**Mistake**: `status` is a raw `string`. The DB row gets updated to whatever was passed, but the `switch` only wires up `"active"` and `"canceled"` — any other value (a typo, a new status like `"past_due"` added later) updates the DB row and silently skips both `enableFeatures`/`disableFeatures`, leaving entitlements out of sync with billing state.
**Consequence**: A canceled subscription can keep features enabled (revenue leak) or an active one can stay locked out (support ticket) — and nothing errors, so it isn't noticed until a customer complains.
**Today**: None.
**Device**: Make `status` a union type and make the switch exhaustive so adding a status without handling it is a compile error, not a runtime silence.

```ts
type SubStatus = "active" | "canceled" | "past_due";
function assertNever(x: never): never { throw new Error(`unhandled status: ${x}`); }
// ...default: assertNever(status);   // poka-yoke: new SubStatus values fail the build until handled [control]
```
Warning-only alternative (log-and-continue) would still let the DB and entitlements diverge silently, so Control is worth the type migration here.

### 6. `applyDiscount` has no bound on `percentOff` — Wrong financial output, silent / Needs a bad input to reach it
**Where**: `benchmarks/fixtures/payments.ts:63-65`
**Mistake**: `percentOff > 100` produces a negative price; a negative `percentOff` increases the price. Nothing stops either from reaching Stripe.
**Consequence**: A coupon code or admin typo of `150` off instead of `15` produces a negative charge amount downstream — plausible-looking, not an obvious crash.
**Today**: None.
**Device**: `if (percentOff < 0 || percentOff > 100) throw new Error(...)`. → **Control**, one line.

## Set aside
- Non-null assertions (`from!`, `to!`) in `transfer` — real, but subsumed by finding #2's transaction/validation rewrite; not worth a separate device.
- Missing input validation on `chargeCustomer`'s `amountCents` (could be 0 or negative) — lower blast radius than the idempotency gap in the same function, folded into finding #3 if you want it in the same diff.

Want me to write this to `docs/poka-yoke/audit-2026-08-22.md`, or apply any of these fixes now?