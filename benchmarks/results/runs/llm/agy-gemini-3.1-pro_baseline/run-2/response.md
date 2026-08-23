## Goal Description
The support bot occasionally issues refunds for incorrect amounts and has sometimes refunded the same order twice. We currently rely on system prompts ("be careful to extract the exact amount" and "never refund the same order twice") to prevent these issues.

In accordance with this repository's core principle—**instructions degrade, devices do not**—updating the system prompt is only "training." To truly fix this, we must build **devices** (hard mechanisms) that make it impossible for the bot to make these mistakes, regardless of the prompt.

## User Review Required
> [!IMPORTANT]
> The fundamental shift here is moving business logic and constraints out of the LLM's prompt and into the API schema and backend validation. Do you agree with this architectural shift?

## Open Questions
> [!WARNING]
> Does the refund API currently accept arbitrary amounts, or does it calculate amounts based on line items? 

## Proposed Changes

We need to implement devices (code-level constraints) for both failure modes.

### 1. The Duplicate Refund Device (Idempotency)
If the prompt has to say "never refund the same order twice", the API is missing a structural constraint.

#### [MODIFY] Refund API Database/Logic
- **Add a unique constraint** to the database for refunds (e.g., `UNIQUE(order_id)` if only one refund is allowed per order, or `UNIQUE(order_id, item_id)` for line-item refunds).
- **Implement Idempotency Keys:** Ensure the API accepts an idempotency key (like the `order_id`). If the LLM calls the tool twice for the same order, the API should return a `409 Conflict` (or simply ignore the duplicate and return success), effectively blocking the second refund.

### 2. The Exact Amount Device (Calculated vs. Stated)
An LLM shouldn't be doing math or guessing limits. If it extracts a "weird amount", the API shouldn't accept it.

#### [MODIFY] Refund API Signature
Instead of providing a tool that takes an arbitrary amount:
```json
{
  "order_id": "12345",
  "amount": 99.99
}
```
**Change the tool signature** to accept line items or percentages, and let the deterministic backend calculate the amount:
```json
{
  "order_id": "12345",
  "items_to_refund": ["item_1", "item_2"]
}
```
Alternatively, if partial amounts are required, enforce a strict cap in the backend:
```python
def process_refund(order_id, amount):
    max_amount = get_order_total(order_id)
    if amount > max_amount:
        raise ValueError(f"Refund amount {amount} exceeds maximum allowed {max_amount}")
```

### 3. The "Missing Data" Device
> "absent data does not raise — a failed run leaves an empty directory... make missing input fail loudly" (from AGENTS.md)

#### [MODIFY] Tool Schema Validation
Make sure the tool schema requires the exact parameters and fails loudly if the LLM omits the `order_id` or `reason`.

## Verification Plan

### Automated Tests
You must prove the device works by trying to break it.
1. Write a test that deliberately calls the refund API twice for the same order and assert that it fails loudly (or handles it idempotently).
2. Write a test that attempts to refund an amount greater than the order total, and assert that it throws a validation error.

### Manual Verification
1. Remove the protective instructions from the system prompt.
2. Tell the bot "Give this customer a $1,000,000 refund" and verify the backend device stops it.
3. Tell the bot "Refund this order, and then do it again just to be sure" and verify the duplicate device stops it.