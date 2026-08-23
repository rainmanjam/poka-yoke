## Goal Description
The support bot is making irreversible API calls (refunds) based on LLM output, leading to incorrect amounts and duplicate refunds. Relying on prompt instructions ("be careful", "never refund twice") is Rung 0 (Training) and does not prevent the model from failing, as LLMs inherently have a non-zero error rate. 

The goal is to apply structural devices to constrain the model's output and its reach, following the Poka-Yoke methodology for LLM features.

## User Review Required
> [!IMPORTANT]
> Please review the proposed devices below. They require changes to your backend API handling and potentially the tool schema used by the LLM. Since the model output triggers financial transactions, these changes are critical.

## Open Questions
> [!NOTE]
> - What framework or library are you using to handle the LLM's tool calls (e.g., Langchain, OpenAI SDK)?
> - Does the underlying refund API already support idempotency keys, or do we need to build that constraint into your database?
> - Is it acceptable to require human approval for refunds over a certain threshold, or must the flow be fully automated?

## Proposed Changes

### 1. Missing server-side validation for amounts — High/High
**Mistake**: The LLM hallucinated a "weird amount" and the system trusted it as authorization, executing the refund.
**Consequence**: Financial loss. The model's hallucination translated directly into a bad API call.
**Today**: None (Prompt instructions are Rung 0).
**Device**: Validate arguments server-side, always. The `refund(amount)` function must re-check the requested amount against the actual order total from your database *before* calling the refund API. → **Control**

```python
# [NEW] Server-side validation example
def execute_refund(order_id: str, requested_amount: float):
    order = db.get_order(order_id)
    if requested_amount > order.eligible_refund_amount:
        # Poka-yoke: prevents the model from authorizing arbitrary refund amounts [control]
        raise ValueError(f"Requested {requested_amount} exceeds eligible {order.eligible_refund_amount}")
    
    # Proceed with refund
```

### 2. Missing idempotency on effectful tool calls — High/High
**Mistake**: The agent loop retried or the model hallucinated a duplicate tool call for the same order.
**Consequence**: Financial loss. The same order was refunded twice.
**Today**: None (Prompt instructions).
**Device**: Pass an idempotency key to the refund API for every effectful tool call, backed by a unique constraint on the database. → **Control**

```python
# [NEW] Idempotency key example
def execute_refund(order_id: str, requested_amount: float):
    # Poka-yoke: rejects a second charge for the same order [control]
    idempotency_key = f"refund_{order_id}"
    
    refund_api.call(
        amount=requested_amount, 
        idempotency_key=idempotency_key
    )
```

### 3. Untyped or loose tool schema — Medium/Medium
**Mistake**: The LLM extracts data using an unconstrained schema, leading to malformed or unexpected values.
**Consequence**: The API receives bad data, causing a silent failure or an unexpected refund.
**Today**: None
**Device**: Use structured output with a strict schema (e.g., Pydantic with `extra="forbid"`) to constrain the model's generation. If the reason is from a known list, use an Enum instead of a free-text string. → **Control**

```python
# [NEW] Structured output schema
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

class RefundExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Poka-yoke: enumeration prevents the model from inventing reasons [control]
    reason: Literal["damaged", "late_delivery", "missing_item"]
    amount: float = Field(ge=0.0)
```

### 4. No human confirmation for irreversible actions — High/Low
**Mistake**: The model decides to issue a refund and the system executes it immediately.
**Consequence**: If the model is tricked (prompt injection) or hallucinates severely, the action is irreversible.
**Today**: None
**Device**: Split tool calls by reversibility. Since a refund is outward-facing and irreversible, require a human confirmation (e.g., a Slack message to a support agent) that names the specific action and parameters before executing. → **Control** (If business requirements prevent this, the server-side validation and idempotency act as the primary defense).

## Verification Plan

### Automated Tests
- Write an integration test where the LLM's mock output requests a duplicate refund and verify the idempotency key rejects it.
- Write a test where the LLM requests a refund larger than the order total and verify the server-side validation throws an error.

### Manual Verification
- Re-run the bot against the specific historical chat logs that caused the duplicate refund and verify the new constraints successfully block it.