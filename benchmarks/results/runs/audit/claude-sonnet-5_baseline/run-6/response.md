I ran the three lenses (contact / fixed-value / motion-step) over the file — the hazard-detector script needs a permission approval I don't have in this session, so this pass is manual, but the file is only 105 lines and I read it in full.

**Scope**: `benchmarks/fixtures/payments.ts`, single file, 105 lines.
**Verdict**: `handleWebhook` never verifies the Stripe signature, so anyone who can reach the endpoint can trigger a real charge for any customer — fix that before anything else.

## Findings

### 1. Webhook accepts unsigned events — Money movement/Silent+trivial
**Where**: `benchmarks/fixtures/payments.ts:93-100`
**Mistake**: POST any JSON body shaped like `{"type":"invoice.paid","data":{"customer":"...","amount":...}}` to the webhook endpoint.
**Consequence**: `chargeCustomer` runs for whatever `customer`/`amount` the attacker supplied — full authorization bypass on a code path that moves money. No error, no log, looks like a normal Stripe event.
**Today**: None.
**Device**: Verify `stripe.webhooks.constructEvent(body, sig, endpointSecret)` before touching `event.data`; reject with 400 on failure → **Control**.

### 2. Self-transfer (or same-account race) mints money — Money movement/Silent+plausible
**Where**: `benchmarks/fixtures/payments.ts:17-35`
**Mistake**: Call `transfer(id, id, amount)`, or two concurrent `transfer` calls that touch the same account.
**Consequence**: `to` is read *before* `from`'s balance is decremented, so the second `update` writes `to.balance + amount` on top of a stale read. For a self-transfer this **creates** `amount` out of nothing (balance 100 → transfer 50 to self → balance 150). For two concurrent transfers out of the same account, it's a classic TOCTOU double-spend/overdraft. There's also no transaction — if the second `update` throws, money leaves `from` and never arrives at `to`.
**Today**: None.
**Device**: Reject `fromAccount === toAccount`; wrap both updates in one DB transaction with a row-level lock or a `WHERE balance >= amount` guarded conditional update → **Control**.
```ts
if (fromAccount === toAccount) throw new Error("cannot transfer to self");
await db.$transaction(async (tx) => {
  const updated = await tx.accounts.updateMany({
    where: { id: fromAccount, balance: { gte: amount } },
    data: { balance: { decrement: amount } },
  });
  if (updated.count === 0) throw new Error("insufficient funds");
  await tx.accounts.update({ where: { id: toAccount }, data: { balance: { increment: amount } } });
});
```

### 3. `chargeCustomer` retries without an idempotency key — Money movement/Silent+easy
**Where**: `benchmarks/fixtures/payments.ts:37-61`
**Mistake**: Any transient error after Stripe has actually processed the charge (timeout, dropped response) triggers the `retry` branch.
**Consequence**: A second, distinct charge is created for the same purchase — this is the exact double-charge shape (queue/timeout redelivery) noted in this project's incident history. Silent: the customer just sees two charges later.
**Today**: None.
**Device**: Pass a deterministic `idempotencyKey` (order/invoice ID, not a random UUID) on every `stripe.charges.create` call, including retries → **Control**. Stripe itself dedupes on that key, so this closes it at the source rather than in app logic.

### 4. Failed charge returns `null` and is swallowed — Silent data corruption/Silent+easy
**Where**: `benchmarks/fixtures/payments.ts:55-61`, called from `benchmarks/fixtures/payments.ts:98`
**Mistake**: Any Stripe error (card decline, network error) falls into `catch`, and with `retry=false` returns `null`.
**Consequence**: `handleWebhook` never checks the return value — an `invoice.paid` event that fails to charge just disappears. No alert, no dead-letter, no record that billing owes a retry.
**Today**: None.
**Device**: Don't swallow the error — rethrow (or return a discriminated result the caller must handle) so `handleWebhook` can log/alert/dead-letter → **Control**.

### 5. `purgeCanceledAccounts()` with no argument purges *everything* — Irreversible data loss/Silent+trivial
**Where**: `benchmarks/fixtures/payments.ts:80-91`
**Mistake**: Call `purgeCanceledAccounts()` — the natural way to invoke "the purge job" — expecting it to no-op or use a sane retention window.
**Consequence**: `olderThan ?? new Date()` means omitting the argument doesn't disable the purge, it maximizes it — every canceled account up to *right now* is hard-deleted via raw SQL. No transaction tying the `SELECT` count to the `DELETE`, no soft-delete, no backup.
**Today**: None.
**Device**: Require the cutoff explicitly (no default), and delete by the exact ID set already fetched instead of re-running the predicate:
```ts
export async function purgeCanceledAccounts(olderThan: Date) {
  const doomed = await db.accounts.findMany({ where: { status: "canceled", canceledAt: { lt: olderThan } } });
  await db.accounts.deleteMany({ where: { id: { in: doomed.map(a => a.id) } } });
  return doomed.length;
}
```
→ **Control**. Also drops the raw-SQL string interpolation pattern (`$executeRawUnsafe` with a template literal) — harmless today because `cutoff` is a `Date`, but it's the exact shape that becomes injectable the day someone threads a user-supplied filter through it.

### 6. `updateSubscription` writes unknown statuses, then silently skips features — Silent data corruption/Silent+easy
**Where**: `benchmarks/fixtures/payments.ts:67-78`
**Mistake**: Call with any status string not exactly `"active"` or `"canceled"` — a typo, a new Stripe status like `"past_due"`, British spelling `"cancelled"`.
**Consequence**: The DB write succeeds unconditionally, but the `switch` has no `default`, so feature enable/disable is silently skipped. A misspelled cancellation leaves paid features on indefinitely (revenue leak); a misspelled reactivation leaves a paying customer locked out.
**Today**: None.
**Device**: Type `status` as a union (`"active" | "canceled" | ...`) and make the switch exhaustive with a `never` check in `default` so an unhandled status fails to compile/throws instead of silently no-oping → **Control**.

## Set aside
- `applyDiscount` has no bounds on `percentOff` (>100 → negative price) — real, but low blast radius unless it's on a hot path; worth a one-line clamp, not worth a full device writeup.
- `chargeCustomer(customerId, amountCents, currency, sendReceipt, retry)` — two trailing booleans is a classic flag-argument contact hazard, but it's subsumed by finding 3 (fixing idempotency changes this signature anyway).
- `handleWebhook` reads `process.env.WEBHOOK_TIMEOUT` and never uses it — dead code, not a hazard.

Want me to write this to `docs/poka-yoke/audit-2026-08-22.md`, or apply any of these devices now? I haven't touched the file yet.