This is `benchmarks/fixtures/payments.ts` — the file's own header says it's a deliberately hazard-rich eval fixture, not code that actually ships. Worth flagging in case that's news. That said, here's the real audit, since finding these is exactly the point.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-22

**Scope**: single file, 105 lines, read directly (not a git diff — file named explicitly).
**Verdict**: the webhook handler will execute a forged charge because it never checks the Stripe signature — fix that first, everything else is secondary.

## Findings

### 1. Webhook accepts unsigned events — Money movement + authz bypass / Trivial
**Where**: `benchmarks/fixtures/payments.ts:93`
**Mistake**: anyone who can reach this endpoint POSTs `{"type":"invoice.paid","data":{"customer":"cus_victim","amount":1}}` and it is trusted as if Stripe sent it.
**Consequence**: attacker-controlled `chargeCustomer` calls against arbitrary customer IDs — real charges, no proof they originated from Stripe. Completely silent; looks like normal traffic in logs.
**Today**: None.
**Device**: verify with `stripe.webhooks.constructEvent(body, sig, secret)` and reject on failure → **Control**.
```ts
export async function handleWebhook(rawBody: string, signature: string) {
  const event = stripe.webhooks.constructEvent(rawBody, signature, process.env.STRIPE_WEBHOOK_SECRET!);
  ...
}
```

### 2. `purgeCanceledAccounts()` deletes everything when called with no argument — Irreversible data loss / Silent+plausible
**Where**: `benchmarks/fixtures/payments.ts:80-88`
**Mistake**: call `purgeCanceledAccounts()` (the natural call, e.g. from a cron with no args) — `cutoff` defaults to `new Date()`, so the predicate becomes "every canceled account, regardless of age," and it's gone via raw `DELETE`.
**Consequence**: total, irreversible loss of every canceled account. No dry run, no soft delete, no undo.
**Today**: None.
**Device**: require an explicit retention window, ban a same-as-now cutoff, and drop the raw SQL for the ORM call so the counted set and the deleted set are provably the same query → **Control**.
```ts
export async function purgeCanceledAccounts(retentionDays: number) {
  if (retentionDays < 30) throw new Error("retention window too short");
  const cutoff = new Date(Date.now() - retentionDays * 86_400_000);
  const { count } = await db.accounts.deleteMany({
    where: { status: "canceled", canceledAt: { lt: cutoff } },
  });
  return count;
}
```
Also note the current code independently rebuilds the same predicate twice — once in `findMany`, once hand-strung into raw SQL. They can drift, and `doomed.length` would silently misreport what was actually deleted.

### 3. `chargeCustomer` has no idempotency key — Money movement / Automatic, not even a mistake required
**Where**: `benchmarks/fixtures/payments.ts:44-49`, compounded by the retry at `:56-57` and webhook redelivery at `:98`
**Mistake**: nothing — this fires on its own. Stripe redelivers webhooks; the internal `retry` param resends on failure; neither passes an idempotency key.
**Consequence**: same invoice charged twice. This is the exact shape of a real double-charge incident, just with the network hiccup supplied for free by retries instead of a human.
**Today**: None.
**Device**: derive a stable key (event ID, or `customerId+amount+invoiceId`) and pass `{ idempotencyKey }` to Stripe → **Control**. Also stop swallowing the error to `null` — log it or rethrow so a permanent failure isn't invisible to the caller.

### 4. `transfer(fromAccount, toAccount, amount)` — Money movement / corruption / Easy typo + no atomicity
**Where**: `benchmarks/fixtures/payments.ts:17-35`
**Mistake**: two adjacent same-typed string params — `transfer(b, a, amt)` silently reverses direction, ships as a passing-looking call. Separately, the debit and credit are two independent `update()` calls with no transaction: a crash or throw between them debits the source and never credits the destination.
**Consequence**: money vanishes or moves backwards, and the balance check itself is a TOCTOU race — two concurrent transfers can both pass the check against the same stale balance.
**Today**: None.
**Device**: brand the IDs so they aren't interchangeable, and wrap both updates in one DB transaction → **Control**.
```ts
type AccountId = string & { readonly __brand: "AccountId" };
await db.$transaction(async (tx) => {
  const from = await tx.accounts.findUniqueOrThrow({ where: { id: fromAccount } });
  if (from.balance < amount) throw new Error("insufficient funds");
  await tx.accounts.update({ where: { id: fromAccount }, data: { balance: { decrement: amount } } });
  await tx.accounts.update({ where: { id: toAccount }, data: { balance: { increment: amount } } });
});
```

### 5. `updateSubscription` switches on a free-text `status` — Silent wrong state / Easy typo
**Where**: `benchmarks/fixtures/payments.ts:67-78`
**Mistake**: DB write happens unconditionally at `:68`; the `switch` below it has no `default`. Pass `"actve"` (typo) or any status the switch doesn't enumerate — the DB record updates, but neither `enableFeatures` nor `disableFeatures` runs.
**Consequence**: billing status and actual feature access silently diverge — customer paid, features never turned on (or vice versa on cancel).
**Today**: None.
**Device**: a union type instead of `string`, with an exhaustive switch the compiler enforces → **Control**.
```ts
type SubStatus = "active" | "canceled" | "past_due";
export async function updateSubscription(subId: string, status: SubStatus) {
  await db.subscriptions.update({ where: { id: subId }, data: { status } });
  switch (status) {
    case "active": return enableFeatures(subId);
    case "canceled": return disableFeatures(subId);
    case "past_due": return; // explicit no-op, not a fallthrough
    default: { const _exhaustive: never = status; throw new Error(`unhandled status: ${_exhaustive}`); }
  }
}
```

## Set aside
- `applyDiscount` unbounded `percentOff` (can go negative or >100%) — real, but only dangerous if its output feeds a charge amount directly; not shown here. Worth a one-line clamp if it does.
- Unused `timeout` variable in `handleWebhook` — dead code, not a hazard on its own, but suggests a timeout guard was intended and never wired up.

Want me to write this to `docs/poka-yoke/audit-2026-08-22.md`, or is the conversation copy enough? And separately — since this is a benchmark fixture, do you want it treated as production code to actually patch, or left as-is for the eval?