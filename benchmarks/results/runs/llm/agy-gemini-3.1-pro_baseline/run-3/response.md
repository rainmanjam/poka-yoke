## Goal Description
The support bot is currently relying on system prompt instructions to avoid refunding incorrect amounts and double-refunding orders. According to the Poka-Yoke philosophy, **"instructions degrade and devices do not."** Prompt engineering is just training for the model, and it will eventually fail. 

This plan proposes replacing these fragile instructions with robust, system-level devices (Controls) that make these mistakes impossible.

## User Review Required
> [!IMPORTANT]  
> Are you able to modify the downstream `Refund API` backend, or do we need to implement these devices purely within the bot's middleware/API client? Modifying the backend is the strongest form of Poka-Yoke.

## Open Questions
> [!WARNING]  
> Do we want to support partial refunds? If a customer asks for a partial refund, how should the bot calculate it? Should the bot pass a percentage rather than an absolute amount to minimize hallucination risks?

## Proposed Changes

### 1. Prevent Double Refunds (Idempotency & State Checks)
Instead of telling the bot "never refund the same order twice", we will use a **Control** device to make it structurally impossible.

*   **Backend Approach (Preferred):** Add an idempotency key to the Refund API or enforce a state check. If an order is already fully refunded, the API should return a `409 Conflict` or `400 Bad Request`.
*   **Middleware Approach:** Wrap the API call in the bot's tool definition. Before calling the Refund API, query the order status. If `order.refunded == true`, short-circuit and return an error to the bot.

#### [MODIFY] bot_tools/refund.py (Example)
```python
def process_refund(order_id: str, amount: float):
    # Device: Pre-flight state check (Control)
    order = get_order(order_id)
    if order.status == 'refunded' or order.refundable_amount == 0:
        return "ERROR: This order has already been refunded."
    
    # ... proceed with API call ...
```

### 2. Prevent "Weird Amounts" (Data Validation & Bounds)
Instead of telling the bot "be careful to extract the exact amount", we constrain the possible inputs.

*   **Hard Bounds:** The Refund API (or the tool wrapper) must strictly validate that `amount <= order.refundable_amount`.
*   **Type Constraints:** Ensure the tool schema strongly types the amount as a float and perhaps requires the currency code to match the order.
*   **Approval Workflow (Warning Device):** For refunds above a certain threshold (e.g., $100), the bot cannot execute the API directly. Instead, it transitions to a "draft" state that a human support agent must click "Approve" on.

#### [MODIFY] bot_tools/refund.py (Example)
```python
def process_refund(order_id: str, amount: float):
    order = get_order(order_id)
    
    # Device: Hard bounds check (Control)
    if amount > order.refundable_amount:
        return f"ERROR: Requested amount {amount} exceeds refundable amount {order.refundable_amount}."
        
    if amount <= 0:
        return "ERROR: Refund amount must be greater than 0."
```

## Verification Plan
A Poka-Yoke device is only a device if you can prove it fails when it should.

### Automated Tests
*   `test_double_refund_fails()`: Attempt to process a refund for an order that is already refunded. Assert that the operation is blocked and fails loudly.
*   `test_excessive_refund_fails()`: Attempt to process a refund for `order_total + 1`. Assert that the operation is blocked.

### Manual Verification
*   Trigger the bot in the staging environment and ask it to refund an already refunded order.
*   Ask the bot to refund an amount larger than the original purchase.
*   Verify that in both cases, the bot explains to the user that it cannot perform the action due to system constraints.