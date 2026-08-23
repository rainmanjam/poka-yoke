## Goal Description
The objective is to reliably prevent double-charging customers when the payment worker experiences timeouts or retries, while ensuring legitimate repeat transactions are not blocked. 

The current mitigation (checking for a recent charge of the same amount) is insufficient because:
1. **False Positives (Blocking legitimate charges):** If a customer legitimately buys two items of the same price in quick succession (or the same item twice), the second charge will be incorrectly blocked.
2. **Race Conditions (Time-of-check to time-of-use):** If the queue redelivers the message and two workers process the same event concurrently, they might both check the database, see no prior charge, and both proceed to charge the customer.

The correct, industry-standard approach is to use **Idempotency Keys** provided by payment gateways like Stripe.

## User Review Required
> [!WARNING]
> **Database Schema Change:** This plan requires adding an `idempotency_key` column to your events/messages table, or passing a unique `eventId` from your queue to be used as the idempotency key. Please review the proposed architecture to ensure your queue provides a unique message/event ID.

## Open Questions
> [!IMPORTANT]
> 1. Does your queue system provide a unique `message_id` or `event_id` that is consistent across retries?
> 2. Do you currently store a record of the original event that triggered the charge? 
> 3. Are you using the official Stripe Node.js SDK (or equivalent for your language)?

## Proposed Changes

### Queue/Worker Layer
Instead of generating a new transaction ID per attempt, we must generate a unique key *per logical action* (e.g., the specific queue message ID) and pass it to the billing module.

#### [MODIFY] Worker processing logic
```typescript
// Instead of:
// await chargeCustomer(customerId, amount);

// Do this:
// The messageId remains the same even when the queue redelivers the timed-out message.
const idempotencyKey = queueMessage.messageId; 
await chargeCustomer(customerId, amount, "usd", true, idempotencyKey);
```

---

### Billing Module
We will update the payment integration to accept an idempotency key and forward it to Stripe. Stripe will recognize duplicate requests with the same key and return the original successful response without creating a second charge.

#### [MODIFY] Payment Module (e.g., `payments.ts`)
```typescript
export async function chargeCustomer(
  customerId: string,
  amountCents: number,
  currency = "usd",
  sendReceipt = true,
  idempotencyKey?: string // [NEW] Accept idempotency key
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
    // Retry logic can remain or be offloaded to the queue. 
    // If it retries with the same idempotencyKey, Stripe handles it safely.
    throw e; 
  }
}
```

## Verification Plan

### Automated Tests
1. **Mock Stripe to timeout:** Configure the Stripe mock to delay response past the worker's timeout threshold on the first attempt, but succeed on the second attempt.
2. **Assert single charge:** Verify that despite the queue redelivering the message, Stripe's API is only successfully charged once (the second call with the same idempotency key will return the cached result of the first, or process safely if the first truly failed).
3. **Assert same-amount legit charges:** Send two distinct queue messages for the same customer and same amount (different message IDs). Assert that *both* go through successfully, proving the heuristic bug is fixed.

### Manual Verification
1. Enqueue a payment task.
2. Pause the worker's network connection to Stripe midway to force a timeout.
3. Allow the queue to redeliver the task.
4. Verify in the Stripe Dashboard that only one charge appears for the customer.