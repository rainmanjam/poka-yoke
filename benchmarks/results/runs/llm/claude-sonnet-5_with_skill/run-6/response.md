Good — you've already found the mistake for yourself: adding "be careful" and "never refund twice" to the system prompt. Per this skill, **prompt instructions are rung zero** — they're a comment, not a device, and they will not drive an LLM's error rate to zero. Here's what's actually happening and what to build instead.

## The two hazards

**Weird refund amount**
- *Defect*: customer refunded the wrong amount.
- *Mistake*: the bot parses a dollar figure out of free-form chat text.
- *Hazard*: the amount is generated prose, not a value checked against anything real. There's nothing stopping the model from reading "I paid $900 for two of these" and extracting `900` when the order total was `90`, or hallucinating a number that was never in the message.

**Duplicate refund**
- *Defect*: same order refunded twice.
- *Mistake*: the bot called the refund API a second time for an order it had already refunded.
- *Hazard*: the refund call has no idempotency key and the API has no constraint preventing a second successful refund on the same order. Nothing outside the model's own memory of the conversation stops the repeat call — and conversation memory is exactly the kind of state that gets lost on a retry, a reload, or a second chat session about the same order.

## Devices, ranked by rung

1. **Structured output over prose parsing (Control).** Stop extracting a number from text. Use tool/function-calling with a schema — `refund_amount: float`, `reason: Literal[...]` — so the model can't emit `"nine hundred dollars"` or malformed output. This alone kills a class of "weird amount" bugs, but it only makes the *shape* correct, not the *value*.

2. **Server-side validation against the order, not the model's number (Control).** The model's extracted amount is a client input, not authorization. Look up the order, compute what's actually refundable (paid amount minus any prior refunds), and clamp or reject the call if the model's number doesn't fit — never pass the model's number straight to the payment API. Better still: don't let the model specify a raw dollar amount at all — have it choose "full refund" / "partial — which line items" from the order's real data, so there's no free-form number to hallucinate.

3. **Idempotency key + unique constraint (Control).** Give every refund call an idempotency key derived from the order ID, backed by a unique constraint (e.g. `UNIQUE(order_id)` if only one refund is ever allowed, or `UNIQUE(order_id, idempotency_key)` if partial refunds are legitimate). This is the fix for "never refund twice" — not a prompt line, a constraint the second call physically cannot get past. This is the same hazard as the double-charge case in `retro`: an optional/absent idempotency key on an effectful call, at higher retry rates than any human path.

4. **Confirmation gate on the action itself (Control/Warning depending on amount).** Refunds are irreversible and outward-facing — per this mode's rule, that means a human confirmation naming the exact order and amount before it fires, at least above some threshold. If full autonomy is the point of the bot, at minimum log the pending action and require confirmation for anything above your normal refund size.

5. **Turn both incidents into eval cases (Detection, but load-bearing).** Add the exact production inputs that caused the weird amount and the duplicate call as held-out eval cases run in CI on every prompt/model change. You can't unit-test the model, but you can stop this exact regression silently reappearing next time someone tweaks the prompt.

The prompt edits you made aren't wasted — keep them, they're free and they help — but none of them are why this stops happening. Items 2 and 3 are the two that actually make the specific failures you saw impossible rather than just less likely. Want me to look at the actual extraction/refund-call code and turn this into a concrete diff?