**Using poka-yoke/llm to audit your support bot** — your issues are textbook LLM side-effect hazards with simple, high-rung fixes.

Your problem: **prompt instructions are rung zero** — they have no teeth. "Be careful" and "never do X" are training, not devices.

Here are the gaps:

## 1. Weird refund amounts
**The mistake:** Model extracts `123.45`, but parses it as `12345` or `1.2345`.  
**Today:** Nothing until it reaches your API, which executes blindly.  
**Rung 0 → Rung 1 (Control):**
- Use **structured output** with a schema: `{order_id: str, amount_cents: int, reason: str}`. Constrained decoding makes most malformed extracts unrepresentable.
- **Validate server-side** before calling the refund API: check the amount against the actual order amount. If they don't match, reject or escalate. The model is a client; never trust its numbers.

## 2. Duplicate refunds (the bigger hazard)
**The mistake:** Model calls `refund(order_123)`, network hiccup, system retries, second refund goes through.  
**Today:** Nothing. It charged twice.  
**Rung 0 → Rung 1 (Control):**
- **Idempotency key on every refund call**: use the order ID as the key, backed by a unique constraint in your refunds table (`UNIQUE(order_id, refund_reason)` or similar). Same order + same reason = idempotent; retry safely.
- If your refund API doesn't support idempotency keys yet, add them. This is table-stakes for any irreversible operation that touches money.

## 3. Validate extraction, not intent
Stop asking the model to be careful. Instead:
- Require the model to return a choice from a **known list** of refund reasons (enum, not free text).
- Make amount a bounded integer (`Field(ge=100, le=999999)` for cents) — narrows the mistake surface.

## Why you hit this  
You shipped an action tool (refund) without the control layer. The model has no way to get it right; you've just made careful extraction more important to blame for. The system design is the problem, not the prompt.

Ship these three fixes and the issue becomes impossible rather than just less likely.