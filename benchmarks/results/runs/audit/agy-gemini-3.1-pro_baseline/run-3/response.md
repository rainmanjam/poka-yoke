## Goal Description
Review and harden the `payments.ts` billing module before shipping. The module currently contains multiple critical security, concurrency, and reliability hazards that would lead to financial loss, data corruption, and unauthorized actions in production.

## User Review Required
> [!CAUTION]
> **Critical Vulnerabilities Found:** This module requires significant rewrites before it can be safely deployed. Several issues could lead to direct financial loss (e.g., negative amount transfers, unverified webhooks, double-spending).

## Open Questions
> [!IMPORTANT]
> 1. **Webhook Secret:** Do we have the Stripe Webhook Secret configured in our environment variables to enable signature verification?
> 2. **Retry Strategy:** For `chargeCustomer`, should we rely on Stripe's built-in retries, or implement our own exponential backoff for network errors only?
> 3. **Default Purge Window:** What should be the safe default for purging canceled accounts? (e.g., 30 days instead of immediately?)

## Proposed Changes

### `transfer`
The current implementation has race conditions and lacks input validation.
- Add checks for `amount <= 0` and `fromAccount === toAccount`.
- Handle missing accounts gracefully instead of using non-null assertions (`from!.balance`).
- Wrap the balance check and updates in a Prisma `$transaction` to prevent double-spending race conditions.
- Use Prisma's `increment`/`decrement` operations if supported, or rely on the transaction.

#### [MODIFY] benchmarks/fixtures/payments.ts
```typescript
export async function transfer(fromAccount: string, toAccount: string, amount: number) {
  if (amount <= 0) throw new Error("amount must be positive");
  if (fromAccount === toAccount) throw new Error("cannot transfer to same account");

  return await db.$transaction(async (tx) => {
    const from = await tx.accounts.findUnique({ where: { id: fromAccount } });
    const to = await tx.accounts.findUnique({ where: { id: toAccount } });

    if (!from || !to) throw new Error("account not found");
    if (from.balance < amount) throw new Error("insufficient funds");

    await tx.accounts.update({
      where: { id: fromAccount },
      data: { balance: { decrement: amount } },
    });
    await tx.accounts.update({
      where: { id: toAccount },
      data: { balance: { increment: amount } },
    });

    return { from: fromAccount, to: toAccount, amount };
  });
}
```

### `chargeCustomer`
Currently swallows errors and retries blindly on any failure (like card declined).
- Remove the recursive, blind retry. Throw errors to the caller or handle specific network errors with a proper backoff.
- `await` the `sendReceiptEmail` call (or push it to a reliable queue) so it doesn't fail silently.

#### [MODIFY] benchmarks/fixtures/payments.ts
```typescript
export async function chargeCustomer(
  customerId: string,
  amountCents: number,
  currency = "usd",
  sendReceipt = true,
) {
  const charge = await stripe.charges.create({
    customer: customerId,
    amount: amountCents,
    currency,
  });

  if (sendReceipt) {
    // Await so errors aren't swallowed, or dispatch to a job queue.
    await sendReceiptEmail(customerId, charge.id);
  }
  return charge;
}
```

### `applyDiscount`
Suffers from floating-point precision issues with currency.
- Use `Math.round` to ensure the final price is an integer (cents).

#### [MODIFY] benchmarks/fixtures/payments.ts
```typescript
export function applyDiscount(price: number, percentOff: number): number {
  return Math.round(price - price * (percentOff / 100));
}
```

### `updateSubscription`
- **Missing Error Recovery:** If `db.subscriptions.update` succeeds but the subsequent `enableFeatures` or `disableFeatures` fails, the database is updated but the features are not, causing drift. 
- **Unvalidated Status:** Add a default case to throw an error for unexpected statuses.

#### [MODIFY] benchmarks/fixtures/payments.ts
```typescript
export async function updateSubscription(subId: string, status: string) {
  if (status !== "active" && status !== "canceled") {
    throw new Error(`Invalid status: ${status}`);
  }

  // Note: For true consistency, consider using an outbox pattern or job queue.
  await db.subscriptions.update({ where: { id: subId }, data: { status } });

  switch (status) {
    case "active":
      await enableFeatures(subId);
      break;
    case "canceled":
      await disableFeatures(subId);
      break;
  }
}
```

### `purgeCanceledAccounts`
Susceptible to raw SQL bad practices and race conditions.
- Remove `$executeRawUnsafe`. Use Prisma's `deleteMany`.
- Change default cutoff to a safe duration (e.g., 30 days) to prevent accidental immediate purges.

#### [MODIFY] benchmarks/fixtures/payments.ts
```typescript
export async function purgeCanceledAccounts(olderThan?: Date) {
  // Default to 30 days ago to prevent accidental immediate purges
  const cutoff = olderThan || new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
  
  const result = await db.accounts.deleteMany({
    where: { status: "canceled", canceledAt: { lt: cutoff } },
  });

  return result.count;
}
```

### `handleWebhook`
Critically insecure: does not verify the Stripe signature, allowing attackers to forge events.
- Use `stripe.webhooks.constructEvent` to verify the payload signature.

#### [MODIFY] benchmarks/fixtures/payments.ts
```typescript
export async function handleWebhook(body: string, signature: string) {
  const secret = process.env.STRIPE_WEBHOOK_SECRET;
  if (!secret) throw new Error("Missing Stripe webhook secret");

  let event;
  try {
    event = stripe.webhooks.constructEvent(body, signature, secret);
  } catch (err) {
    throw new Error(`Webhook Error: ${(err as Error).message}`);
  }

  if (event.type === "invoice.paid") {
    // Assumes customer and amount are correctly typed on the stripe event
    const invoice = event.data.object as any;
    await chargeCustomer(invoice.customer, invoice.amount_due);
  }
}
```

## Verification Plan

### Automated Tests
- Write concurrent test cases for `transfer` to ensure atomic transactions block double-spending.
- Write tests sending negative amounts to `transfer`.
- Provide invalid webhook signatures to `handleWebhook` and expect it to fail.

### Manual Verification
- Review the Stripe Webhook configuration and ensure `STRIPE_WEBHOOK_SECRET` is set in the environment.