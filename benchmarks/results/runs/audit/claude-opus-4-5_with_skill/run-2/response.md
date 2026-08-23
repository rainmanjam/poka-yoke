I've read the skill and references. Now running the poka-yoke analysis on your billing module.

**Scope**: `benchmarks/fixtures/payments.ts` — billing module, 105 lines, 7 exports.

This file has real problems. The nervousness is justified. Here's what can bite you:

---

## Findings

### 1. `transfer()` — No transaction (F5) — **Blast: money loss / Ease: high**
**Where**: `payments.ts:25-30`
**Mistake**: First update succeeds, second fails (network, constraint, anything). Money debited from source, never credited to destination.
**Consequence**: Silent money loss. The return value says success. No way to detect without reconciliation.
**Today**: None
**Device**: Wrap both updates in `db.$transaction([...])` → **Control**

```ts
await db.$transaction([
  db.accounts.update({ where: { id: fromAccount }, data: { balance: { decrement: amount } } }),
  db.accounts.update({ where: { id: toAccount }, data: { balance: { increment: amount } } }),
]);
```

---

### 2. `transfer(from, to)` — Swappable IDs (C1) — **Blast: wrong direction / Ease: high**
**Where**: `payments.ts:17`
**Mistake**: Call `transfer(destinationId, sourceId, amount)` — compiles, passes review, sends money backwards.
**Consequence**: Silent. Plausible-looking wrong result. Both values are strings.
**Today**: None
**Device**: Branded types `SourceAccountId` / `DestAccountId`, or an object argument `{ from, to, amount }` so call sites self-document → **Control** / **Warning**

---

### 3. `chargeCustomer()` — Swallowed error returns null (X1) — **Blast: lost revenue / Ease: high**
**Where**: `payments.ts:55-60`
**Mistake**: Charge fails, function returns `null`, caller doesn't check, order marked paid anyway.
**Consequence**: Silent lost revenue. The non-retry path returns `null` as if that's a valid charge.
**Today**: None
**Device**: Throw on failure. If you must absorb some errors, discriminate by type and log/alert. Never return `null` for "failed" — use a Result type or throw → **Warning**

---

### 4. `purgeCanceledAccounts()` — Default deletes everything (F2+F3) — **Blast: data loss / Ease: one forgotten arg**
**Where**: `payments.ts:80-81`
**Mistake**: Call `purgeCanceledAccounts()` with no argument. `olderThan` defaults to `new Date()` = now. Deletes ALL canceled accounts.
**Consequence**: Irreversible bulk delete. The default for a destructive operation is the most destructive choice.
**Today**: None
**Device**: Make `olderThan` required (no default). Add a row-count guard: refuse if > N rows unless `force: true` → **Control**

```ts
async function purgeCanceledAccounts(olderThan: Date, opts?: { maxRows?: number }) {
  const count = await db.accounts.count({ where: { status: "canceled", canceledAt: { lt: olderThan } } });
  if (count > (opts?.maxRows ?? 100)) throw new Error(`Refusing to delete ${count} rows — pass maxRows to override`);
  // ...
}
```

---

### 5. `chargeCustomer()` — No idempotency key (M2) — **Blast: double-charge / Ease: any retry**
**Where**: `payments.ts:37, 57`
**Mistake**: Network blip on first call, retry fires, both succeed. Customer charged twice.
**Consequence**: Visible to customer. Refund required. Trust damage.
**Today**: None
**Device**: **Required** `idempotencyKey` parameter passed to Stripe. Back with DB unique constraint on `(customer_id, idempotency_key)` so the second attempt fails at the database → **Control**

---

### 6. `updateSubscription()` — Non-exhaustive switch (F1) — **Blast: features misconfigured / Ease: add a status**
**Where**: `payments.ts:70-77`
**Mistake**: Someone adds `"past_due"` or `"trialing"` status. Switch silently falls through. Features stay enabled for unpaid subscriptions.
**Consequence**: Silent. Revenue leakage or compliance issue.
**Today**: None
**Device**: Discriminated union for status + `assertNever` default arm. Adding a variant now breaks the build → **Control**

```ts
type SubStatus = "active" | "canceled" | "past_due" | "trialing";
// ...
default: assertNever(status);
```

---

### 7. `handleWebhook()` — Unvalidated JSON (C7) — **Blast: crash or wrong charge / Ease: malformed payload**
**Where**: `payments.ts:94`
**Mistake**: Stripe sends a malformed event (or an attacker does). `JSON.parse` throws or fields are missing. Also: no signature verification.
**Consequence**: Crash, or if fields happen to exist, charges wrong customer/amount.
**Today**: None
**Device**: Zod schema at the boundary. Verify Stripe signature before parsing. Only handle known event types → **Control**

---

### 8. `transfer()` — Check-then-act race (M5) — **Blast: negative balance / Ease: concurrent calls**
**Where**: `payments.ts:21-28`
**Mistake**: Two transfers from same account interleave. Both pass the balance check, both debit. Balance goes negative.
**Consequence**: Money created from nothing. Reconciliation nightmare.
**Today**: None
**Device**: Atomic update with condition: `UPDATE ... SET balance = balance - $1 WHERE balance >= $1 RETURNING *`. If no row returned, insufficient funds → **Control**

---

## Set aside (3)

- `applyDiscount(price, percentOff)` — swappable numbers, but local math helper, low blast
- `sendReceiptEmail` fire-and-forget — should log failures, but not money-losing
- `process.env.WEBHOOK_TIMEOUT` read and ignored — dead code, not a hazard

---

`★ Insight ─────────────────────────────────────`
The pattern linking findings 1, 5, and 8: **billing code that reads and then writes is almost always wrong**. The time between read and write is where money bugs live. The fix is always the same: make it atomic (conditional update, transaction, idempotency key enforced at DB level).
`─────────────────────────────────────────────────`

**Verdict**: Don't ship this. The transaction-less `transfer()` and the `purgeCanceledAccounts()` default are incident-grade. Fix those two before merge; the others are real but won't cause a 3am page on day one.

Want me to write the fixes, or do you want to take a pass at the top 2-3 first?