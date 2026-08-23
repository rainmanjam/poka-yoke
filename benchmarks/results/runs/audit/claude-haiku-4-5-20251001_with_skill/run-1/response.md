**Scope**: `benchmarks/fixtures/payments.ts` — the billing module fixture (105 lines)

This file is deliberately hazard-rich, and your instinct is right. I've found **5 critical issues** that would silently corrupt money or authorization. Here's the priority-ranked audit:

---

### 1. SQL Injection in `purgeCanceledAccounts` — Irreversible data loss / Very easy
**Where**: `benchmarks/fixtures/payments.ts:86–87`
**Mistake**: A caller provides a date; the function interpolates it directly into a raw SQL string without escaping.
**Consequence**: Silent. An attacker or confused log entry could DELETE everything. The function returns a plausible number of rows.
**Today**: None
**Device**: Use parameterized queries (Prisma's built-in protection) → **Control**

```ts
// Replace lines 86–87 with:
await db.$executeRaw`DELETE FROM accounts WHERE status = 'canceled' AND canceled_at < ${cutoff}`;
```

---

### 2. Non-atomic transfer loses money on any error — Irreversible data loss / Medium ease
**Where**: `benchmarks/fixtures/payments.ts:17–35`
**Mistake**: Debit one account, then network hiccup before crediting the other.
**Consequence**: Money vanishes silently. Balance sheets never reconcile.
**Today**: None (no transaction wrapping)
**Device**: Wrap both updates in a transaction; add a compensating transfer or ledger entry on failure → **Control**

```ts
await db.$transaction([
  db.accounts.update({ where: { id: fromAccount }, data: { balance: from!.balance - amount } }),
  db.accounts.update({ where: { id: toAccount }, data: { balance: to!.balance + amount } }),
]);
```

---

### 3. Webhook double-charge via unidempotent retry — Irreversible money loss / Very easy
**Where**: `benchmarks/fixtures/payments.ts:93–100`
**Mistake**: `handleWebhook` calls `chargeCustomer`, which retries on any error without checking if Stripe already succeeded.
**Consequence**: Customer charged twice, silent. Appears in Stripe logs as two separate charges.
**Today**: None
**Device**: Add idempotency key to the webhook call; use `chargeCustomer(customerId, amountCents, currency, sendReceipt, false)` (no retry) and let Stripe's idempotency protect the retry → **Control**

```ts
// Add idempotency key (e.g. event.id) to prevent re-charging
// Use retry=false since Stripe idempotency handles it
await chargeCustomer(event.data.customer, event.data.amount, "usd", true, false);
```

---

### 4. Swappable account IDs in `transfer` — Silent data corruption / Medium ease
**Where**: `benchmarks/fixtures/payments.ts:17`
**Mistake**: Pass `transfer(toId, fromId)` by accident. Both are strings; TypeScript sees nothing wrong.
**Consequence**: Money moves backward silently. No validation catches it.
**Today**: None
**Device**: Use branded newtype IDs instead of bare strings → **Control**

```ts
type FromAccountId = string & { readonly __brand: "FromAccountId" };
type ToAccountId = string & { readonly __brand: "ToAccountId" };

export async function transfer(from: FromAccountId, to: ToAccountId, amount: number) {
  // ...
}
```

---

### 5. Unvalidated webhook body and Stripe data — Authorization bypass / Very easy
**Where**: `benchmarks/fixtures/payments.ts:93–99`
**Mistake**: `JSON.parse(body)` throws if body is malformed. `event.data.customer` and `event.data.amount` are unchecked. Webhook is never authenticated.
**Consequence**: Invalid charges, wrong customers billed, or crash. No signature verification.
**Today**: None
**Device**: Validate webhook signature (Stripe provides `stripe.webhooks.constructEvent`), validate schema with Zod/Joi, use exhaustive destructuring → **Control**

```ts
import { z } from "zod";

const WebhookEventSchema = z.object({
  type: z.literal("invoice.paid"),
  data: z.object({
    customer: z.string(),
    amount: z.number().int().positive(),
  }),
});

export async function handleWebhook(body: string, signature: string) {
  const event = stripe.webhooks.constructEvent(body, signature, process.env.WEBHOOK_SECRET);
  const parsed = WebhookEventSchema.parse(event);
  
  if (parsed.type === "invoice.paid") {
    await chargeCustomer(parsed.data.customer, parsed.data.amount, "usd", true, false);
  }
}
```

---

### 6. Money as `number` instead of cents-as-int — Silent rounding errors / Easy
**Where**: `benchmarks/fixtures/payments.ts:12, 17, 39, 63–64`
**Mistake**: Store or pass money as `number`. `0.1 + 0.2 !== 0.3` in floating point.
**Consequence**: Rounding errors compound in ledgers. Reconciliation fails silently.
**Today**: None
**Device**: Always store money as cents (integers), type-checked → **Control**

```ts
type CentsAmount = number & { readonly __brand: "CentsAmount" };
function toCents(dollars: number): CentsAmount {
  return Math.round(dollars * 100) as CentsAmount;
}
```

---

### 7. Unhandled enum branch in `updateSubscription` — Silent logic skip / Medium ease
**Where**: `benchmarks/fixtures/payments.ts:67–77`
**Mistake**: Add a new status like `"paused"`, but forget the switch case. Features neither enable nor disable.
**Consequence**: Subscription status changes, but features remain in wrong state. Silent.
**Today**: None
**Device**: Use TypeScript discriminated union or `satisfies` to enforce exhaustiveness → **Control**

```ts
type SubscriptionStatus = "active" | "canceled" | "paused";

export async function updateSubscription(subId: string, status: SubscriptionStatus) {
  await db.subscriptions.update({ where: { id: subId }, data: { status } });

  switch (status) {
    case "active":
      await enableFeatures(subId);
      break;
    case "canceled":
      await disableFeatures(subId);
      break;
    case "paused":
      // handle pause
      break;
    // TS error if a case is missing
  }
}
```

---

### 8. Boolean flag parameters in `chargeCustomer` — Confusing call sites / Easy
**Where**: `benchmarks/fixtures/payments.ts:37–43`
**Mistake**: Call `chargeCustomer(id, 1000, "usd", false, true)` and forget what each boolean means.
**Consequence**: Send receipt to wrong customer, or retry unexpectedly.
**Today**: None
**Device**: Replace boolean flags with a named options object → **Control**

```ts
export async function chargeCustomer(
  customerId: string,
  amountCents: number,
  options?: { currency?: string; sendReceipt?: boolean; retry?: boolean }
) {
  const { currency = "usd", sendReceipt = true, retry = false } = options ?? {};
  // ...
}
```

---

### 9. Unvalidated `chargeCustomer` retry logic — Double charge / Medium ease
**Where**: `benchmarks/fixtures/payments.ts:55–60`
**Mistake**: `catch` swallows all errors, returns `null`, and conditionally retries. Caller never knows if charge succeeded.
**Consequence**: Caller retries if they see `null`, not knowing Stripe already succeeded.
**Today**: None (retry param exists but is error-prone)
**Device**: Use idempotency keys in the Stripe call itself, remove the retry param, let Stripe handle it → **Control**

---

## Set aside

- **Unused `timeout` env var** (`line 95`): No consequence today; low priority.
- **Unguarded `from!` and `to!` non-null assertions** (`lines 21, 27, 31`): If either query returns null, crash (loud). Better as Control with proper error, but not silent.

---

## Next steps

These five critical findings (SQL injection, non-atomic transfer, unidempotent retry, swappable IDs, unvalidated webhook) all reach **Control** and ship with the code. None require a runtime assertion; all can be caught at compile time or schema time.

Would you like me to:
1. Apply these fixes to the fixture so it becomes a safety reference?
2. Generate a device registry documenting each fix?
3. Create test cases showing each hazard failing?