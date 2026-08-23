Using the poka-yoke `llm` skill for this — it's an AI feature already in production causing real incidents, so this is audit voice, not build voice.

**The core problem: both of your fixes are rung zero.** "Be careful to extract the exact amount" and "never refund the same order twice" are instructions to a component that has a non-zero error rate on every single call. No prompt wording drives that to zero — it's not a bug in your prompt, it's the nature of the material. You need devices *outside* the model, not better wording inside it.

### 1. Wrong refund amount
**Mistake**: model mis-extracts an amount from ambiguous chat text (e wrong currency, misread digit, hallucinated number).
**Consequence**: refund API gets called with a plausible-looking but wrong number — silent, no error, money moves.
**Today**: None (prompt wording only).
**Device**:
- Use structured/constrained output (schema: `amount: float`, `reason: enum[...]`) instead of parsing prose — this closes the "malformed output" half.
- The half the schema *can't* catch: is the number *correct*. For that, don't trust the model's number as authorization — validate server-side against the actual order: `amount <= order.refundable_balance`, and ideally `amount == order.total` unless the model also returns a specific line-item reason that justifies a partial. The model proposes; your system disposes. → **Control** on "an invented amount reaches Stripe," **Warning at best** on "is this the *right* amount for a legitimate partial refund," which may need a human confirmation step for anything above a threshold or below full amount.

### 2. Double refund on the same order
**Mistake**: the bot (or a retry, or a queue redelivery, or the user re-describing the same complaint two messages later) issues a second refund call for an order that already got one.
**Consequence**: double payout, silent until finance notices.
**Today**: None — "never refund twice" is a sentence in a system prompt, not a check.
**Device**: idempotency key on every refund call, keyed on order ID (or order ID + reason), backed by a unique constraint at the API/DB layer — the same pattern as payment retries. This makes the second call fail loudly or no-op instead of succeeding twice, regardless of whether the model "remembers" it already did this earlier in the conversation. → **Control**.

### Also worth closing while you're in there
- **Tight tool schema**: `refund(order_id: str, amount: float, reason: enum[...])` — no free-text field the model can use to smuggle extra intent, `amount` bounded to the order's refundable range if your framework supports range constraints.
- **Confirmation gate for irreversible action**: since a refund is money leaving and hard to reverse, consider requiring either a second deterministic check (amount matches order records exactly) or human approval above some dollar threshold, rather than trusting the model's decision to fire the tool at all.
- **Turn both production incidents into eval cases**: the specific chat messages that caused the wrong amount and the double refund become permanent regression tests in your eval suite, run in CI on every prompt/model change. That's the only way you'll know a future prompt tweak didn't reopen the same hole.

The prompt edits aren't wasted — keep them, they reduce frequency — but the amount validation and the idempotency key are what actually make the two incidents you already had impossible to repeat, not just less likely.