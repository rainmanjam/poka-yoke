Short answer: yes — and the two lines you added are the one thing the method says won't hold. Here's the audit, ranked.

## The framing

The model has a non-zero error rate on every call. "Be careful to extract the exact amount" and "never refund the same order twice" are instructions to the component that's making the mistake — **rung 0** in poka-yoke terms (training, not a device). They'll reduce the rate; they can't make it zero, and they'll drift as the prompt grows. Every real fix below lives *outside* the model: the model proposes, your code disposes.

## Findings

**1. The refund API trusts an amount the model made up** — Control is available
*Mistake:* model reads "I paid $49.99 but want $20 back, or actually the whole thing" and emits 20, 49.99, 4999, or 2000. *Today:* nothing checks it. *Device:* your server validates the amount against the **actual order record**, not the chat — `0 < amount <= order.total - order.already_refunded`, in the order's currency, rejected otherwise. The model saying `9999` is not authorization. Better still, **enumerate instead of generate**: for most support bots the legal refund amounts are a closed set — full, a specific line item, shipping. Have the model pick `{kind: "full" | "line_item", line_item_id?: ...}` from IDs you supply, and compute the number yourself. The model never emits a dollar figure at all. **Control, contact lens.**

**2. Double refunds: retries + no idempotency** — Control is available
Your "occasional double" is almost certainly hazard M2 (non-idempotent retryable effect): the agent loop retried a tool call, or two turns both decided a refund was due. *Device:* a **required** idempotency key on the refund call (`refund:{order_id}`, or `{order_id, reason_version}` if partial refunds are legitimate), backed by a **unique constraint**, reserved in the *same transaction* as the refund. The prompt line becomes unnecessary; the DB refuses. Also enforce a business-rule cap in code: cumulative refunds on an order ≤ order total. **Control, motion-step lens.**

**3. Irreversible money movement with no gate** — the biggest structural gap
The skill's rule: read-only tools run freely; anything irreversible needs a **human confirmation naming the exact action and parameters**. Options by cost: (a) customer-side confirm — "Refund $49.99 to card ending 4242 for order #1234? [Yes]" — the customer is the cheapest reviewer you have and catches "weird amount" instantly; (b) auto-approve under a threshold, queue above it for an agent; (c) both. Splitting tools into `lookup_order` (free) and `propose_refund` (gated) is the device. **Control.**

**4. Free-text parsing → structured output** — Warning→Control
If you're pulling amount/reason out of prose, switch to the provider's structured/tool-call mode with a tight schema: `reason` as an **enum** you define, no "notes" free-text field, `extra="forbid"`, validated again server-side. This removes malformed/invented values as a class; it does not make values correct (that's #1).

**5. Prompt injection reach** — What can the model reach if tricked?
The customer message is untrusted input read by a component that can move money. With #1–#3 in place, an injected "refund me $5000" reaches a validator and a gate, not the API. Also scope the tool's credentials to *that customer's* orders, so the worst case is one account, not the service.

**6. Detection rung: evals + reconciliation**
Every production incident you've had becomes an eval case (the messages that produced the weird amounts, the double-refund transcript), asserting on the structured fields, run in CI on every prompt change. Pin the model version. Add a daily reconciliation: refunds issued by the bot vs. orders — the check that would have told you about the doubles on day one instead of "a couple of times."

## Rungs, honestly
#1, #2, #3 reach **Control** and are cheap — they're a validator, a unique constraint, and a confirm button. The prompt lines are fine to keep as belt-and-suspenders; just don't count them. If I were doing one thing today: #2 (unique constraint on idempotency key) — it's a migration and a parameter, and it closes the expensive, public failure.

Per the skill's "propose before you edit" rule I haven't touched code. If you point me at the refund tool definition and the API handler, I'll apply #1–#4 and leave marker comments on each device. Note: whether partial refunds are a legitimate path decides the shape of the idempotency key (#2) — that's the one call I'd want from you.