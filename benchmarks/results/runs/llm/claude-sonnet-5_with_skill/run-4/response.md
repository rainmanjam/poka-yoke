Both of those prompt additions are rung 0 — "be careful" and "never do X" are training, and training is exactly what degrades under production load (longer conversations, edge-case phrasing, retried messages). They'll reduce the failure rate, not zero it. Here's what actually closes each hazard, per `poka-yoke:llm`:

**1. Wrong refund amount extraction — mistake: model reads $49.99 or "half of my $80 order" from prose and outputs a hallucinated or misparsed number.**
- Rung 0 today: "extract the exact amount" in the prompt.
- Device: don't let the model's number be authoritative at all. Use structured output (a schema forcing `{order_id: str, reason: str}` — no `amount` field) and have your code look up the actual refundable amount from the order record. If the bot needs to propose an amount (partial refund), still validate server-side: `assert 0 < requested_amount <= order.refundable_balance`, reject anything else. The model is a client; a client's number is never authorization. **Rung: Control**, enforced outside the model.

**2. Double refund — mistake: same order refunded twice, almost certainly a retry (timeout, redelivered message, user resending "please refund me").**
- Rung 0 today: "never refund the same order twice" in the prompt.
- Device: idempotency key on the refund call, keyed on order ID, backed by a unique constraint in your DB/payment provider (Stripe idempotency keys work exactly this way). The second call with the same key either no-ops or returns the original result — the model never gets a chance to cause a duplicate, because the duplicate can't be constructed. **Rung: Control.**

**3. One you haven't mentioned but is the same shape: gate the refund tool call itself.** Refunds are irreversible and outward-facing money movement — per the skill this should require either (a) a tight tool schema (order_id + reason enum, no free-text amount field, amount computed server-side as above) or (b) a confirmation step before the API call fires, naming the exact order and amount. If your bot currently has one broad `issue_refund(amount, reason)` tool the model calls freely, that's the actual root cause — the schema is wide enough to let it.

**4. Detection layer, since you already had two production incidents:** add both bad outputs as eval cases (`extracts wrong amount from ambiguous chat`, `retried request causes duplicate call`) so a future prompt/model change can't silently regress them. Also cap refund amount per call and alert on refund volume per order/user — cheap backstop if the Control-layer check has a bug.

Do you want me to look at the actual bot code (parsing + tool-call site) and implement the schema + idempotency key, or is this still design-stage?