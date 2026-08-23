One thing worth flagging up front: this file's own header comment says it's an "eval fixture... deliberately hazard-rich" for benchmarking — it's not something actually queued to ship. I ran the audit anyway since that's useful either way, but wanted you to know before you route "before we ship it" concerns anywhere real.

# Poka-Yoke Audit — benchmarks/fixtures/payments.ts — 2026-08-22

**Scope**: single file, 105 lines, named explicitly.
**Verdict**: `handleWebhook` charges customers off an unverified request body — that's an unauthenticated-money-movement bug, worse than everything else here combined.

## Findings

### 1. Webhook handler charges customers with no signature verification — Data loss & security/Silent
**Where**: `benchmarks/fixtures/payments.ts:93-100`
**Mistake**: Anyone who can POST JSON to this endpoint sends `{"type":"invoice.paid","data":{"customer":"<any id>","amount":<any amount>}}` and it gets charged — there's no check that the request came from Stripe.
**Consequence**: Arbitrary, attacker-controlled charges against arbitrary customer IDs. Looks completely normal in logs — it's indistinguishable from a real Stripe event.
**Today**: None
**Device** → **Control**: verify `stripe-signature` against the webhook secret before touching `event.data`, reject with 400 on mismatch.
```ts
const sig = req.headers["stripe-signature"];
const event = stripe.webhooks.constructEvent(body, sig, process.env.STRIPE_WEBHOOK_SECRET!);
```
Also: Stripe delivers events at-least-once — dedupe on `event.id` before calling `chargeCustomer`, or the same paid invoice gets charged twice on redelivery.

### 2. `purgeCanceledAccounts()` deletes everything when called with no argument — Irreversible data loss/Silent
**Where**: `benchmarks/fixtures/payments.ts:80-91`
**Mistake**: Call `purgeCanceledAccounts()` — the natural, lazy call — and `cutoff` defaults to `new Date()` (now). Every canceled account satisfies `canceledAt < now`, so this deletes *all* canceled accounts, not "old" ones.
**Consequence**: Full, unrecoverable hard delete via raw SQL, no transaction, no soft-delete, no dry run. The function name suggests routine cleanup; the default makes it total.
**Today**: None
**Device** → **Control**: make the cutoff required, not optional, and enforce a minimum age so `purgeCanceledAccounts(new Date())` can't nuke everything either.
```ts
export async function purgeCanceledAccounts(olderThan: Date) {
  const minAge = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
  if (olderThan > minAge) throw new Error("cutoff must be at least 30 days ago");
  ...
}
```
Secondary issue: the returned count comes from a separate `findMany`, and the actual delete reconstructs its own WHERE clause via raw SQL — if the two conditions ever drift, the reported count and the actual deleted rows silently diverge.

### 3. `transfer` is two non-atomic writes with no locking — Silent money corruption/Silent
**Where**: `benchmarks/fixtures/payments.ts:17-35`
**Mistake**: Two concurrent transfers from the same account both read the balance before either write lands (TOCTOU) — both pass the `insufficient funds` check, both debit, account goes negative with no record of how. Separately: `transfer(id, id, amount)` (self-transfer) reads `from`/`to` as the same stale object, and the second `update` overwrites the first using the stale pre-transfer balance — the debit is silently erased.
**Consequence**: Double-spend under concurrency; silent balance corruption on self-transfer. No error, no log, just a wrong number.
**Today**: None
**Device** → **Control**: single atomic conditional update (or a DB transaction with row locking), and reject `fromAccount === toAccount` explicitly.
```ts
if (fromAccount === toAccount) throw new Error("cannot transfer to self");
await db.$transaction(async (tx) => {
  const debited = await tx.accounts.updateMany({
    where: { id: fromAccount, balance: { gte: amount } },
    data: { balance: { decrement: amount } },
  });
  if (debited.count === 0) throw new Error("insufficient funds");
  await tx.accounts.update({ where: { id: toAccount }, data: { balance: { increment: amount } } });
});
```

### 4. `chargeCustomer` retries without an idempotency key — Silent double charge/Reachable
**Where**: `benchmarks/fixtures/payments.ts:37-61`
**Mistake**: On failure with `retry: true`, it calls `stripe.charges.create` again. If the first call actually succeeded on Stripe's side but the response was lost (timeout, network blip), the retry creates a second real charge.
**Consequence**: Customer billed twice for one purchase — this is the exact shape of the "340 customers double-charged" class of incident, not a hypothetical.
**Today**: None
**Device** → **Control**: pass a stable idempotency key (e.g. derived from the originating request/invoice ID) so Stripe itself collapses the retry into the original charge.
```ts
await stripe.charges.create({ customer: customerId, amount: amountCents, currency }, { idempotencyKey: requestId });
```

### 5. `chargeCustomer` swallows every failure into `null` — Silent revenue loss/Silent
**Where**: `benchmarks/fixtures/payments.ts:55-60`
**Mistake**: `catch (e) { ... return null }` discards the actual error entirely — card declined, invalid customer, Stripe outage, and a genuine bug all look identical to the caller.
**Consequence**: Callers that don't explicitly check for `null` proceed as if billing succeeded (e.g. `handleWebhook` does exactly this — ignores the return value). Failures never surface to anyone.
**Today**: None
**Device** → **Warning** (Control would need call-site changes): log/report `e` before returning, and change the return type to force callers to handle failure explicitly.
```ts
} catch (e) {
  if (retry) return chargeCustomer(customerId, amountCents, currency, sendReceipt, false);
  logger.error("charge failed", { customerId, amountCents, error: e });
  return { ok: false as const, error: e };
}
```
Full control needs `chargeCustomer`'s callers (including `handleWebhook`) updated to branch on the result — that's a ripple beyond this file, flagging rather than doing it silently here.

### 6. `updateSubscription` has a non-exhaustive switch over a bare string — Silent entitlement drift/Reachable
**Where**: `benchmarks/fixtures/payments.ts:67-78`
**Mistake**: `status` is `string`, not a union of Stripe's actual subscription statuses. The DB write happens unconditionally; the switch only knows `"active"` and `"canceled"`. Real Stripe statuses like `"past_due"`, `"trialing"`, `"unpaid"`, `"incomplete_expired"` — or a plain typo — write to the DB and then hit no case at all.
**Consequence**: DB says one thing, feature flags say another, with no error anywhere. A `past_due` customer keeps full access; nobody notices until support escalates.
**Today**: None
**Device** → **Control**: a `SubscriptionStatus` union type plus an exhaustiveness check.
```ts
type SubscriptionStatus = "active" | "canceled" | "past_due" | "trialing" | "unpaid";
switch (status) {
  case "active": ...
  case "canceled": ...
  default: { const _exhaustive: never = status; throw new Error(`unhandled status: ${status}`); }
}
```

### 7. `transfer(fromAccount, toAccount, amount)` — adjacent same-type params — Money movement/Reachable
**Where**: `benchmarks/fixtures/payments.ts:17`
**Mistake**: Both accounts are plain `string`. `transfer(toAccount, fromAccount, amount)` compiles and runs, moving money the opposite direction, silently.
**Consequence**: Reversed transfer, no type error, no runtime error — looks like a normal successful transfer in logs.
**Today**: None
**Device** → **Control**: branded types so a swap is a compile error, not a runtime one.
```ts
type AccountId = string & { readonly __brand: "AccountId" };
export async function transfer(fromAccount: AccountId, toAccount: AccountId, amount: number) { ... }
```

## Set aside
- `chargeCustomer`'s two adjacent booleans (`sendReceipt`, `retry`) — real swap risk, but lower blast radius than #4/#5 on the same function; fix incidentally if you touch this signature for #4.
- `applyDiscount` — no bound on `percentOff`, so a negative value inflates price; low severity, not money-movement.
- `handleWebhook`'s unguarded `JSON.parse` and unused `timeout` variable — crash-on-malformed-body and dead code respectively, both loud/cheap compared to the above.

---

Given the file header, I'd treat this as validation that the fixture actually contains the hazards it claims to (webhook auth, double-charging, non-atomic transfer — all present) rather than a pre-ship gate. If there's a real payments file this stands in for, point me at it and I'll run the same pass. Want me to write this to `docs/poka-yoke/audit-2026-08-22.md`, or is the conversation copy enough?