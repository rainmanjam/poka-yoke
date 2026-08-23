Short answer: the two lines you added are rung zero — they're requests to a component with a non-zero error rate on every call, and they'll stop working on exactly the inputs that already fooled it. Both bugs have real devices, and neither lives in the prompt.

**Verdict:** the model should *propose* a refund; your code should *decide* one. Nothing the model emits should reach the refund API without a server-side check and an idempotency key.

## Findings

### 1. Double refund — money movement / requires only a retry
**Mistake:** the refund tool can be called twice for the same order (agent-loop retry, network timeout → re-call, or the model simply calling it again).
**Today:** None. "Never refund twice" in the prompt is not a device.
**Device:** required idempotency key on the refund API, backed by `UNIQUE (order_id, idempotency_key)` — or simpler for refunds, a `UNIQUE` on `order_id` in the refunds table plus a state check (`order.status = 'refundable'`) in the same transaction as the write → **Control**. The key must be reserved in the same transaction as the effect and the stored result replayed to the second caller, so a retry learns "already done" rather than getting a bare constraint error. Also cap the tool call: one effectful call per conversation, enforced in code.

### 2. Weird amount — money movement / silent and plausible-looking
**Mistake:** the model extracts an amount from prose (wrong currency, "$20 off the $80" → 80, a figure quoted from a previous message, or text a customer wrote to steer it) and the API trusts it.
**Today:** None — the model is a client, and its `amount` is not authorization.
**Device, two layers:**
- **Enumerate rather than generate.** Don't have the model invent an amount. Look up the order server-side and hand it a closed set: `refund_type: Literal["full", "item:<line_id>", "partial"]`, with the amount *computed* from the order. For `partial`, schema-bound the number: `amount: Decimal, gt=0, le=order.total`, `extra="forbid"`. Reject anything outside → **Control** on the shape.
- **Validate against the order in code** — `amount <= order.refundable_balance`, currency matches → **Control** on the value. The schema can't know the value is right; this check can.

### 3. No confirmation gate on an irreversible action — money movement
**Device:** split tools by reversibility. Lookup tools run freely; `issue_refund` above some threshold (or always, to start) requires a human confirmation that names the order, amount and reason → **Control**. If you can't afford a human in the loop, say so — then the order-derived amount in #2 is doing all the work.

### 4. Untrusted text reaches a privileged action — injection
The customer's message is untrusted input feeding a money-moving tool. The devices in #2–#3 are what bound the blast radius; the question isn't "can it be tricked" but "what can it reach if it is." Also scope the refund credential to *that customer's* orders so a tricked model can't refund someone else's.

### 5. No detection rung
Every production failure becomes an eval case: add the exact messages that produced the weird amounts and the double refund to a held-out set, assert on the structured fields, run it in CI, and pin the model version. Without this you have no way to tell whether your prompt edits helped.

**Set aside:** step/token/cost caps on the agent loop (F7) — worth doing, lower blast radius than the above.

**Recap:** the prompt lines are training, not devices. Move the amount decision into code (order-derived, schema-bounded, validated against the order), make the refund idempotent at the database, gate it with a confirmation, and turn the two incidents into CI evals. If you want, share the tool definition and refund handler and I'll sketch the concrete diffs.