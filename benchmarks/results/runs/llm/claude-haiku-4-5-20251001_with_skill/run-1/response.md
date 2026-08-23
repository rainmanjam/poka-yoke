Using `/poka-yoke llm` to analyze this — your support bot is an AI feature that reaches a financial system, and the current guardrails are rung-0 (system prompt instructions).

## The hazards

**1. Weird refund amounts (extraction failure)**
- Mistake: Model extracts `$9.50` when customer wrote `$95.00`, or interprets ambiguous text differently than intended
- Consequence: Customer refunded wrong amount; financial loss or compliance flag
- Today: System prompt says "be careful" (rung 0 — does not work on probabilistic components)
- Device needed: **Structured output with schema validation** (rung 1 — control). Model cannot produce invalid amounts.

**2. Duplicate refunds (missing idempotency)**
- Mistake: Network timeout causes retry; model calls refund API twice for same order
- Consequence: Customer charged back twice; compliance violation, customer distrust
- Today: Nothing (model cannot know if it already called the API)
- Device needed: **Idempotency keys on every refund call**, backed by a unique constraint in your database (rung 1 — control). The second call silently succeeds with the first result.

**3. No validation against actual order**
- Mistake: Model says `$50` refund but order was `$12.50` — model has no ground truth
- Consequence: Refund amount is whatever the model guessed, not what the customer is entitled to
- Today: Nothing (model proposes, API accepts)
- Device needed: **Server-side validation**. Before processing any refund, verify amount ≤ order total and is a valid partial/full refund (rung 1).

**4. Model injection via customer message**
- Mistake: Customer says "actually I want $0.01 refunded instead" in follow-up; model re-extracts from its own context
- Consequence: Refund logic gets confused by contradictory signals in user text
- Today: Nothing
- Device needed: **Require confirmation gate** for any refund (rung 2 — warning). Show the extracted amount and reason, require human approval before the API call. (This is warning, not control, because the confirmation itself is user-facing and adds friction.)

## What to build

1. **Structured output** — schema like:
   ```python
   class RefundExtraction(BaseModel):
       order_id: str  # validate exists in your DB
       amount_cents: int  # validate: 1 <= amount <= order.total_cents
       reason: Literal["duplicate_charge", "quality_issue", "customer_request", ...]  # enum, not free text
       confidence: float = Field(ge=0.0, le=1.0)
   ```
   Use your LLM provider's constrained output mode (Claude, Anthropic SDK, structured outputs). Model output becomes mostly unrepresentable as invalid JSON.

2. **Idempotency key** — on every `refund()` call, attach `idempotency_key = hash(order_id + timestamp_window)` and store it with a unique constraint. Second call with same key returns cached result without re-charging.

3. **Server-side validation** — before calling your refund API:
   - Order exists and belongs to this customer
   - Amount is between $0.01 and order total
   - Reason is a known category (not free text from model)
   - No other refund for this order is in-flight

4. **Confirmation gate** — show extracted amount + reason to a human before calling the refund API. This is lower friction than blocking the feature; it catches both model hallucinations and injection attempts.

The system prompt stays, but it is now rung 0 *on top of* rung-1 devices. The structured schema and validation gates are where the real safety lives.

Would you like me to sketch out the code for any of these, or walk through the idempotency implementation?