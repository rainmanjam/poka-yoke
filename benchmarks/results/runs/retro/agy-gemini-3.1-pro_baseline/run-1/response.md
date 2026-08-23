## Fixing Payment Double Charges using Idempotency

The heuristic check you added (looking for a recent charge of the same amount) is **not enough** and is fundamentally unsafe for a few reasons:

1. **Race Conditions:** If the queue redelivers the message rapidly, two worker instances could run simultaneously. Both would check the database for a recent charge, both would see nothing, and both would issue a charge to Stripe.
2. **False Positives:** If a customer legitimately makes two identical purchases in a short timeframe (e.g. buying a ticket, then immediately deciding to buy a second one for a friend), your check will block the second valid charge.
3. **Eventual Consistency:** If you are reading from a replica, the first charge might not be visible yet when the second attempt checks the database.

The industry-standard solution for this exact problem is to use **Idempotency Keys**. 

### How Stripe Idempotency Keys Work
When you include an `Idempotency-Key` header in your request, Stripe caches the result. If a request with the exact same key is sent again within 24 hours, Stripe returns the original cached response instead of processing a new charge. This perfectly solves the "timeout and retry" problem because the retry will simply fetch the result of the first attempt.

---

## User Review Required

> [!IMPORTANT]
> The idempotency key must be tied to the **unique event or order**, not randomly generated at the time the charge request is made. If you generate a random UUID right before calling Stripe, retries will get a different UUID and you will double-charge again. Do you currently have a unique identifier on your queue messages (e.g., `event_id`, `order_id`, or `invoice_id`) that we can use?

> [!WARNING]
> If your worker updates local database state after the Stripe charge (e.g., updating an order status), you also need to make the worker idempotent locally. If the worker crashes *after* Stripe succeeds but *before* the DB update, the next retry will get the cached Stripe success, but we must ensure we don't accidentally send the user two receipts or fulfill the order twice.

---

## Open Questions

> [!NOTE]
> 1. What does the queue message payload look like? Is there a unique `message_id` or `transaction_id` we can extract?
> 2. Are you using the official Stripe Node.js SDK? The plan assumes you are, as it natively supports idempotency keys.

---

## Proposed Changes

### Payment Module
Implementing the idempotency key in the Stripe charge function.

#### [MODIFY] payments.ts
We need to update the `chargeCustomer` signature (and any callers) to accept an idempotency key and pass it in the Stripe request options.

```typescript
// benchmarks/fixtures/payments.ts (or your actual worker file)

export async function chargeCustomer(
  customerId: string,
  amountCents: number,
  idempotencyKey: string, // [NEW] Require an idempotency key
  currency = "usd",
  sendReceipt = true,
  retry = false,
) {
  try {
    const charge = await stripe.charges.create(
      {
        customer: customerId,
        amount: amountCents,
        currency,
      },
      {
        idempotencyKey, // [NEW] Pass to Stripe
      }
    );

    if (sendReceipt) {
      void sendReceiptEmail(customerId, charge.id);
    }
    return charge;
  } catch (e) {
    // If we retry, we must reuse the exact same idempotencyKey!
    if (retry) {
      return chargeCustomer(customerId, amountCents, idempotencyKey, currency, sendReceipt, false);
    }
    return null;
  }
}
```

#### [MODIFY] worker handler
Where you consume the queue message, you must pass the message's unique identifier as the idempotency key.

```typescript
// Example Worker Update

export async function handleWebhook(body: string) {
  const event = JSON.parse(body);
  
  if (event.type === "invoice.paid") {
    // Use the unique event ID (or invoice ID) as the idempotency key
    await chargeCustomer(
      event.data.customer, 
      event.data.amount,
      event.id // MUST be a unique, consistent ID for this exact transaction
    );
  }
}
```

---

## Verification Plan

### Automated Tests
1. **Mock Stripe to timeout:** We will write a test that mocks the Stripe API to timeout on the first call and succeed on the second call.
2. **Assert on idempotency key:** We will verify that both the initial call and the retry call passed the exact same `Idempotency-Key` to the mocked Stripe client.
3. **Assert single execution:** We will verify that local side-effects (like DB updates or email receipts) are only triggered once.

### Manual Verification
1. Enqueue a payment task in a staging environment.
2. Intercept the network request to Stripe and drop it (or force the worker to crash after calling Stripe).
3. Let the queue redeliver the message.
4. Verify in the Stripe Dashboard (Staging) that only a single charge was created, and that the second request shows in the logs as an "Idempotent Replayed" response.