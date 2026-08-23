Now I have all the context. Running the analysis through the three poka-yoke lenses on your billing module.

`★ Insight ─────────────────────────────────────`
This file is **deliberately hazard-rich** (the comment at line 1-4 says so). But these are all hazards that pass code review regularly. Let me show you what the three lenses find.
`─────────────────────────────────────────────────`

---

## Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-20

**Scope**: payments.ts billing module, 105 lines  
**Verdict**: The `transfer()` function can lose money on partial failure — two writes with no transaction. Fix that first.

---

### Findings

#### 1. Non-atomic transfer — **Blast: catastrophic / Ease: inevitable**
**Where**: `payments.ts:25-32`  
**Mistake**: First update succeeds, second fails (network, DB timeout, process crash).  
**Consequence**: Money leaves `fromAccount` but never arrives at `toAccount`. Silent loss. Unrecoverable without manual reconciliation.  
**Today**: None  
**Device**: Wrap in `db.$transaction()` → **Control**

```ts
await db.$transaction(async (tx) => {
  await tx.accounts.update({ where: { id: fromAccount }, data: { balance: { decrement: amount } } });
  await tx.accounts.update({ where: { id: toAccount }, data: { balance: { increment: amount } } });
});
```

#### 2. Double-charge on retry — **Blast: catastrophic / Ease: common**
**Where**: `payments.ts:56-58`  
**Mistake**: Network timeout after Stripe succeeds → `catch` → `retry=true` → charges again.  
**Consequence**: Customer billed twice. Refund plus chargeback risk.  
**Today**: None  
**Device**: **Required** idempotency key backed by unique index → **Control**

```ts
async function chargeCustomer(
  customerId: string,
  amountCents: number,
  idempotencyKey: string,  // required, not optional
  currency: Currency,
  // ...
) {
  await stripe.charges.create({ ..., idempotency_key: idempotencyKey });
```

Control requires database-side `UNIQUE(customer_id, idempotency_key)` so the app can't skip it.

#### 3. Unbounded purge with SQL injection — **Blast: catastrophic / Ease: one call**
**Where**: `payments.ts:80-91`  
**Mistake**: Call `purgeCanceledAccounts()` with no argument → deletes all canceled accounts up to NOW. Plus `$executeRawUnsafe` with string interpolation → SQL injection.  
**Consequence**: Mass irreversible data loss. Attacker-controlled cutoff date.  
**Today**: None  
**Device**: (a) Make `olderThan` required, (b) parameterized query, (c) row-count guard → **Control**

```ts
export async function purgeCanceledAccounts(olderThan: Date, options: { maxRows?: number } = {}) {
  const max = options.maxRows ?? 100;
  const count = await db.accounts.count({
    where: { status: "canceled", canceledAt: { lt: olderThan } },
  });
  if (count > max) throw new Error(`Refusing to purge ${count} rows (limit ${max})`);
  // Use parameterized delete, not raw SQL
  await db.accounts.deleteMany({ where: { status: "canceled", canceledAt: { lt: olderThan } } });
}
```

#### 4. Race condition on balance check — **Blast: high / Ease: under load**
**Where**: `payments.ts:21-28`  
**Mistake**: Two concurrent transfers both read balance 100, both pass `< amount` check, both deduct → balance goes negative.  
**Consequence**: Overdraft, downstream accounting mismatch.  
**Today**: None  
**Device**: Atomic conditional update with row locking → **Control**

```ts
const updated = await tx.accounts.updateMany({
  where: { id: fromAccount, balance: { gte: amount } },
  data: { balance: { decrement: amount } },
});
if (updated.count === 0) throw new Error("insufficient funds");
```

#### 5. Swappable from/to accounts — **Blast: high / Ease: silent**
**Where**: `payments.ts:17`  
**Mistake**: `transfer(destinationId, sourceId, 500)` — reversed arguments compile and run.  
**Consequence**: Money flows backward. Plausible wrong answer, discovered by customer complaint.  
**Today**: None  
**Device**: Branded types so `AccountId` is distinct from `string` → **Control**

```ts
type AccountId = string & { readonly __brand: "AccountId" };
async function transfer(from: AccountId, to: AccountId, amount: Cents): Promise<TransferResult>
```

#### 6. Charge errors swallowed as `null` — **Blast: high / Ease: every failure**
**Where**: `payments.ts:55-60`  
**Mistake**: Stripe throws (declined card, rate limit, invalid customer) → `catch` → `return null`.  
**Consequence**: Caller cannot distinguish "declined" from "network error" from "bug". Billing silently fails.  
**Today**: None  
**Device**: Re-throw or return discriminated union → **Warning** (runtime)

```ts
type ChargeResult = 
  | { ok: true; charge: Stripe.Charge }
  | { ok: false; error: "declined" | "network" | "invalid_customer"; message: string };
```

#### 7. Non-exhaustive status switch — **Blast: medium / Ease: next variant**
**Where**: `payments.ts:70-77`  
**Mistake**: Add status `"paused"` or `"past_due"` → switch falls through silently.  
**Consequence**: Features remain enabled for unpaid accounts.  
**Today**: None  
**Device**: `assertNever` + `Status` union type → **Control**

```ts
type SubscriptionStatus = "active" | "canceled" | "paused" | "past_due";

switch (status) {
  case "active": /* ... */ break;
  case "canceled": /* ... */ break;
  default: assertNever(status); // compile error when variant added
}
```

#### 8. Unvalidated webhook — **Blast: medium / Ease: any malformed payload**
**Where**: `payments.ts:93-100`  
**Mistake**: Malformed JSON or missing fields → throws deep inside handler, or passes wrong data to `chargeCustomer`.  
**Consequence**: Crash or silent wrong charge. No signature verification either.  
**Today**: None  
**Device**: Zod schema at boundary + Stripe signature verification → **Control**

```ts
const WebhookEvent = z.object({
  type: z.literal("invoice.paid"),
  data: z.object({ customer: z.string(), amount: z.number() }),
});
const event = WebhookEvent.parse(JSON.parse(body));
```

---

### Set aside (lower priority)

- **C2**: Boolean flags `sendReceipt`, `retry` — unreadable call sites, but won't cause silent money loss
- **C5**: `balance: number` vs `amountCents` — unit confusion possible, but less critical than the above
- **M6**: `void sendReceiptEmail()` — fire-and-forget, but receipt failure isn't billing-critical
- **F4**: `process.env.WEBHOOK_TIMEOUT` read inside handler — lazy config, but unused anyway
- **X4**: `from!.balance` non-null assertions — will throw, but at least it throws (not silent)

---

### Summary by rung

| Rung | Count | What's needed |
|------|-------|---------------|
| **Control** | 7 | Transaction, idempotency key, branded types, exhaustive switch, schema validation, atomic update, required params |
| **Warning** | 1 | Discriminated union for charge errors (runtime only) |
| **Detection** | 0 | — |
| **None** | 8 | Current state |

Your instinct was right. The top four findings (#1-4) are all money-critical and currently have **no protection at all**. Want me to apply any of these devices?