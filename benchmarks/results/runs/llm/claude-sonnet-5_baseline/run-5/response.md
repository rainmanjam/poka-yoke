Two prompt additions won't fix this — they're rung zero. "Be careful" and "never twice" are requests to a component that has a non-zero error rate on *every* call; no wording drives that to zero. The fix is structural, outside the model, on both failure modes you're seeing:

**Wrong amount extracted → force structured output, then validate it against ground truth**
- Stop parsing prose for the amount/reason. Use the provider's structured-output/tool-calling mode with a strict schema: amount as a `number` with min/max bounds, reason as an `enum` of your actual refund reasons (not free text). Malformed shapes become unrepresentable instead of occasionally slipping through.
- That schema only proves the output is *well-formed*, not *correct*. The model saying `amount: 500` is not authorization — your refund handler must independently look up the order and cap the refund at what's actually refundable (order total minus prior refunds). Never trust the number the model extracted as the source of truth; treat it as a proposed value the server re-derives or at least clamps.

**Double refunds → idempotency key with a unique DB constraint**
- This is a classic retry/race bug, not a reasoning bug — a device fixes it completely where a prompt instruction can only reduce its odds. Generate an idempotency key from the order ID (e.g. `refund:{order_id}`) and pass it to your payment processor's idempotency-key parameter, *and* enforce a unique constraint on `(order_id)` or `(order_id, refund_type)` in your own refunds table before you ever call the API. Two calls with the same key/order collapse into one refund regardless of how many times the bot decides to call the tool.

**Two more worth adding while you're in there:**
- Reversibility gate: refunds are outward-facing and hard to reverse, so put a ceiling on what the bot can do autonomously — e.g. auto-execute under some dollar threshold, require human confirmation above it. That bounds the blast radius of any single bad extraction.
- Turn these two production incidents into permanent eval cases (the exact weird-amount transcript, the exact double-refund transcript) that run in CI on every prompt/model change — so a future prompt edit can't silently reintroduce either.

★ Insight ─────────────────────────────────────
The reason "never refund twice" degrades over a long session is that it's competing for attention with everything else in the context window — it's advisory text the model has to remember to apply, not a constraint it's structurally unable to violate. An idempotency key backed by a unique constraint doesn't compete for attention; it's enforced by the database regardless of what the model "remembers."
─────────────────────────────────────────────────

Want me to look at your actual extraction/refund code and wire up the schema + idempotency key?