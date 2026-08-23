Using `poka-yoke:llm` — your two bugs are different classes and only one of them is even partly a prompt problem.

**The prompt lines are rung zero.** "Be careful to extract the exact amount" is a request to a component with a non-zero error rate. It helps a little; it isn't a device. A device is outside the model.

## 1. Wrong amount — stop letting the model produce the number

The model currently *generates* a dollar figure from prose. Instead have it **select**: given the order's line items, the model returns line item IDs and a reason code from a fixed enum. Your server computes the amount from the order record.

```python
class RefundProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str
    line_item_ids: list[str]          # must exist on that order
    reason: Literal["damaged", "late", "not_received", "wrong_item", "other"]
    full_order: bool = False
```

No free-text amount field means no hallucinated amount. Then server-side, unconditionally: the order belongs to this chat's authenticated customer, every line item ID exists on it, and `amount <= order.refundable_balance`. The model is a client; a client's input is never authorization.

Anything above a threshold, or `reason == "other"`, goes to a human who sees the specific amount and order before it fires.

## 2. Double refund — this is not an LLM bug at all

It's the classic one. An idempotency key on the refund API call, backed by a **unique database constraint**. Key it on something stable — `(order_id, line_item_ids_hash)` or a conversation-turn ID — not on a generated UUID, which changes on retry and defeats the point.

A "check if already refunded, then refund" read is a TOCTOU race, not a device. Two concurrent turns both pass the check. Only the constraint is a device — it's the one thing that can't be raced.

★ Insight ─────────────────────────────────────
Your `.remember/` notes from this morning show the same shape in the double-charge incident (queue redelivery, 340 customers): interim dup-check insufficient, fix was idempotency keys + unique constraint. Same hazard, different entry point. If that key scope is still undecided, decide it once for both paths.
─────────────────────────────────────────────────

## 3. Turn both incidents into eval cases

You can't patch the model, so the regression test *is* the fix. Take the actual production transcripts that produced wrong amounts, freeze them as an eval set asserting on the structured fields, and gate prompt/model changes in CI on it. Pin the model version while you're there — a silent provider update is an unannounced deploy of your least predictable component.

---

**The decision that's yours, not mine:** what counts as "the same refund"? If a customer legitimately asks for a second partial refund on the same order an hour later, a key of `(order_id, line_items)` blocks it. Too narrow and duplicates slip through; too broad and you block real work. That depends on your refund policy — I'd need to know whether repeat partials on one order are a real flow before picking.