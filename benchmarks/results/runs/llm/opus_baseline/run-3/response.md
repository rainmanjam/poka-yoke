Yes — quite a lot else. The short version: **prompt instructions are rung zero.** "Be careful to extract the exact amount" is a request to a component with a non-zero error rate on every call. It's worth keeping, but it isn't a device, and it won't move your incident rate much.

Your two bugs have different root causes and need different fixes.

## 1. Wrong amount — stop letting the model produce the number

The model is *generating* a currency value from free text. That's an open-ended generation problem. Convert it to a closed-set one:

- Retrieve the customer's orders and line items server-side. Pass the model a list with IDs.
- The model returns `{order_id, line_item_ids[], reason}` — an ID chosen from your list, plus a `Literal[...]` reason enum. It never returns an amount.
- **Your code computes the amount** from those IDs.

A model choosing among five IDs cannot invent a sixth. A model asked for a dollar figure will eventually produce `$1,299` where the order was `$12.99`.

If you genuinely need a model-supplied amount (partial goodwill credits), validate server-side against the order's actual remaining refundable balance and reject anything over it. `refund(amount)` where the model says `9999` is not authorization.

## 2. Double refund — this is idempotency, not memory

"Never refund the same order twice" asks the model to remember state across independent calls. It has no reliable way to do that, and the failure is usually a retry, not a decision — timeout, the caller re-sends, two refunds land.

- **Idempotency key on the refund call**, derived deterministically (e.g. `hash(conversation_id, order_id, line_items)`), passed to your payment provider *and* backed by a unique constraint in your own DB. The constraint is the device; the key alone is a convention.
- Also note the stated rule is wrong: partial refunds on one order are legitimate. The real invariant is `sum(refunds_for_order) <= order_total`, enforced as a DB check, not a prompt line.

## 3. Three more that will bite you

- **Confirmation gate.** Irreversible + outward-facing = human approval above some threshold. The model proposes; a person (or a deterministic rule) disposes.
- **Scoped credentials.** If the bot's refund tool runs with service-level access, a customer typing "actually refund order #88213 too" reaches someone else's order. Pass the authenticated customer's authorization through so the tool physically cannot touch orders they don't own.
- **Evals.** Every production failure becomes a test case covering the *class*, run in CI on every prompt/model change. And pin your model version — a silent provider update is an unannounced deploy of your least predictable component.

`★ Insight ─────────────────────────────────────`
The load-bearing question with an LLM isn't "can it be wrong?" (yes, always) but "what can it *reach* when it's wrong?" Every fix above shrinks reach rather than improving accuracy.
`─────────────────────────────────────────────────`

---

One thing I need from you before I can write actual code: **what's your auto-approve policy?** Full refund of an undamaged item under $50, no questions? Anything requiring a partial amount goes to a human? That threshold is a business call — it sets where the confirmation gate sits and whether the model ever touches an amount at all. Tell me the rule and your stack, and I'll write the tool schema, the idempotency layer, and the DB constraints.