Excellent — I have the skill and hazard catalog loaded. Running the three poka-yoke lenses over this billing module.

`★ Insight ─────────────────────────────────────`
This file is deliberately hazard-rich (per the comment), but these are **exactly** the patterns that ship in real billing code. The transfer function alone combines three classic hazards that have caused real outages: swappable IDs, race conditions, and non-atomic writes.
`─────────────────────────────────────────────────`

---

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-20

**Scope**: Single file, 105 lines, billing module  
**Verdict**: The `transfer()` function can lose money under concurrency and the `purgeCanceledAccounts()` function will delete ALL canceled accounts when called without a date.

## Findings

### 1. Non-atomic transfer creates/destroys money — Irreversible/Silent

**Where**: `payments.ts:25-32`  
**Mistake**: Two separate `UPDATE` statements without a transaction. Failure after the first write leaves money debited but never credited.  
**Consequence**: Money vanishes (or doubles on a retry). Silent — no error thrown, partial state persists.  
**Today**: None  
**Device**: Wrap in `db.$transaction()` → **Control**

```ts
await db.$transaction(async (tx) => {
  await tx.accounts.update({ where: { id: fromAccount }, data: { balance: { decrement: amount } } });
  await tx.accounts.update({ where: { id: toAccount }, data: { balance: { increment: amount } } });
});
```

### 2. Check-then-act race on balance — Irreversible/Concurrent

**Where**: `payments.ts:21-26`  
**Mistake**: Balance checked at line 21, debited at line 26. Concurrent transfers can both pass the check.  
**Consequence**: Account goes negative. Silent.  
**Today**: None  
**Device**: `SELECT FOR UPDATE` inside transaction, or a database `CHECK (balance >= 0)` constraint → **Control**

### 3. `purgeCanceledAccounts()` default deletes ALL canceled accounts — Irreversible/Easy

**Where**: `payments.ts:80-91`  
**Mistake**: `olderThan` defaults to `new Date()` (now). Calling `purgeCanceledAccounts()` with no argument deletes every canceled account, not "old" ones.  
**Consequence**: Mass data loss. The function signature lies — it suggests "optional" means "reasonable default," but the default is catastrophic.  
**Today**: None  
**Device**: Make `olderThan` required with no default. Add row-count confirmation above a threshold. → **Control**

```ts
export async function purgeCanceledAccounts(olderThan: Date, options: { confirm: true })
```

### 4. SQL injection in `purgeCanceledAccounts` — Security/Easy

**Where**: `payments.ts:86-88`  
**Mistake**: `$executeRawUnsafe` with string interpolation. A crafted `cutoff` Date with a malicious `toISOString()` override could inject SQL.  
**Consequence**: Data exfiltration or destruction.  
**Today**: None  
**Device**: Use parameterized query: `$executeRaw\`DELETE ... WHERE canceled_at < ${cutoff}\`` → **Control**

### 5. `chargeCustomer` has no idempotency key — Irreversible/Retry

**Where**: `payments.ts:37-61`  
**Mistake**: The `retry` parameter retries without an idempotency key. Queue redelivery or UI double-click can double-charge.  
**Consequence**: Customer charged twice. Support ticket, refund, trust damage.  
**Today**: None  
**Device**: Add **required** `idempotencyKey: IdempotencyKey` parameter backed by a unique constraint → **Control**

### 6. Swallowed exception returns null — Silent/Easy

**Where**: `payments.ts:55-60`  
**Mistake**: `catch (e) { return null }` hides Stripe errors (card declined, network, fraud).  
**Consequence**: Caller receives `null`, interprets as "no charge happened," proceeds without payment. Silent.  
**Today**: None  
**Device**: Distinguish "retriable error" from "terminal failure." Only `return null` for known-safe cases; rethrow otherwise → **Warning** (specific catch types) or **Control** (Result type)

### 7. Swappable `fromAccount`/`toAccount` — Money/Typo

**Where**: `payments.ts:17`  
**Mistake**: Both parameters are `string`. A typo `transfer(to, from, amount)` compiles.  
**Consequence**: Money flows backward. Silent.  
**Today**: None  
**Device**: Branded types `SourceAccountId` / `DestAccountId` → **Control**

```ts
type SourceAccountId = Brand<string, "SourceAccountId">;
type DestAccountId = Brand<string, "DestAccountId">;
```

### 8. `updateSubscription` non-exhaustive switch — Future/Silent

**Where**: `payments.ts:70-77`  
**Mistake**: Only handles `"active"` and `"canceled"`. A new status like `"paused"` falls through silently.  
**Consequence**: Features not enabled/disabled correctly for new states. Silent.  
**Today**: None  
**Device**: Add `default: assertNever(status as never)` after typing `status` as a union → **Control**

### 9. Stringly-typed `status` in `updateSubscription` — Typo/Silent

**Where**: `payments.ts:67`  
**Mistake**: `status: string` accepts any spelling. `"cancelled"` (UK spelling) passes.  
**Consequence**: Falls through the switch, no action taken. Silent.  
**Today**: None  
**Device**: `status: "active" | "canceled" | "paused"` union type → **Control**

### 10. Fire-and-forget `sendReceiptEmail` — Reliability/Silent

**Where**: `payments.ts:51`  
**Mistake**: `void sendReceiptEmail(...)` — floating promise. Errors vanish; if the process exits, email is lost.  
**Consequence**: Customer never gets receipt. Silent unless you grep logs.  
**Today**: None  
**Device**: Enable `@typescript-eslint/no-floating-promises` as error. Queue the email in a transaction outbox → **Warning** (lint) / **Control** (outbox)

### 11. Unvalidated webhook body — Security/Easy

**Where**: `payments.ts:93-99`  
**Mistake**: `JSON.parse(body)` into `any`, no signature verification, no schema.  
**Consequence**: Attacker posts a fake "invoice.paid" event, triggers free service.  
**Today**: None  
**Device**: Verify Stripe signature with `stripe.webhooks.constructEvent()`, parse into a zod schema → **Control**

### 12. Unused `WEBHOOK_TIMEOUT` — Code smell

**Where**: `payments.ts:95`  
**Mistake**: `process.env.WEBHOOK_TIMEOUT` read but never used.  
**Consequence**: Dead code, but also suggests intended-but-unfinished timeout handling.  
**Today**: N/A  
**Device**: Remove or implement → not a poka-yoke finding, just cleanup

---

## Set aside

- `applyDiscount` has swappable parameters (both `number`) — low risk since it's pure math and likely internal.
- `Account.balance` is `number` not a `Money` type — real hazard, but lower blast radius than the above.
- Boolean flags `sendReceipt`, `retry` — readability issue, not catastrophic.

---

## Summary by Rung

| Rung | Count | Key examples |
|------|-------|--------------|
| **Control needed** | 9 | Transaction, idempotency key, branded IDs, schema validation |
| **Warning acceptable** | 2 | Lint rules for floating promises, swallowed errors |
| **None today** | 11 | This file has no mistake-proofing devices |

**The three that need fixing before ship:**
1. **`transfer()` non-atomic** — will lose money under load
2. **`purgeCanceledAccounts()` default** — one careless call deletes everything  
3. **`chargeCustomer()` no idempotency** — retries double-charge

Want me to propose the specific code changes for any of these? I'll wait for your go-ahead before editing.