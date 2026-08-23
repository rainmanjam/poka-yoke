★ Insight ─────────────────────────────────────
Prompt guardrails ("be careful," "never refund twice") are **rung zero** — training that degrades. The moment an LLM has even a 0.1% error rate, you cannot rely on instructions. You need structural devices outside the model. This bot is issuing money, so both problems demand **Control** rung (impossible) or **Warning** rung (caught immediately), not prose requests.
─────────────────────────────────────────────────

Your two bugs are different shapes:

## 1. Wrong refund amount (contact lens — can the wrong thing fit?)

**The mistake:** Bot extracts "refund $50" from messy chat, model hallucinates slightly, calls API with $500 or $5.

**Today:** Prompt says "be careful." The model still does this occasionally.

**Device:** Structured output + server-side validation. **Control rung.**

- Constrain the model to output a schema (amount as a bounded number, not free text):
  ```python
  class RefundRequest(BaseModel):
      order_id: str
      amount_cents: int = Field(ge=1, le=500000)  # max $5000
      reason: str
  ```
- **Server-side check before the API call:** Look up the actual order. Reject any amount that doesn't match a valid refund target (full refund, or a refund reason that permits partial with a max). This catches both hallucination and edge cases where the order genuinely changed.
- If the model's extracted amount doesn't match a valid option, reject it with a clear message — don't silently clamp or round.

## 2. Duplicate refunds (motion-step lens — can steps happen in the wrong order or be skipped?)

**The mistake:** Model decides to refund again, or a network timeout causes a retry, and the API is called twice for the same order.

**Today:** Prompt says "never refund the same order twice." Still happens — maybe the model doesn't know it already processed it, maybe a retry loop fires, or maybe the bot runs twice on the same message.

**Device:** Idempotency keys + unique constraint in your DB. **Control rung.**

- Every `refund(order_id, amount)` call gets an idempotency key (use order_id as the key or `sha256(order_id + timestamp)` if order can be refunded multiple times legitimately).
- Add a **unique constraint** on `(order_id, idempotency_key)` in your refunds table.
- When the same key arrives twice, the DB constraint fires — the second call fails, and your retry logic either returns the original result or errors cleanly.
- This survives network timeouts, bot restarts, prompt injection, and hallucination. The second refund becomes physically impossible.

## Summary

- **Amount:** Structured schema + server-side order lookup (Control). Drops hallucinated amounts before they reach the API.
- **Duplicates:** Idempotency keys + DB constraint (Control). Makes the second refund unrepresentable in your system.

Both devices sit *outside* the model. Prompts can stay as guidance, but the system itself now stops the mistake. That is the difference between training and a device.