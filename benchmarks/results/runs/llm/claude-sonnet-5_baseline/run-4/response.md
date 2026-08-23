Prompt instructions are rung zero — they reduce the error rate but can't drive it to zero, and both of your failures are exactly the kind that survive prompting because the constraint lives outside the model, not inside it. Here's what actually closes each hole:

**Wrong amount extraction**
- Stop parsing/trusting prose. Force the model to call a structured tool (`propose_refund(order_id, amount_cents, reason)`) via function-calling / constrained output, with a JSON schema — not "extract the amount and I'll parse your reply."
- Validate server-side, always: `amount_cents` must be `> 0` and `<= order.total_paid`, and `order_id` must exist and belong to this conversation's customer. The model saying `9999` is not authorization — it's a proposal.
- Where possible, don't let the model invent the amount at all: have it choose from a small enumerated set (e.g. "full refund" / "partial — user-specified line item") derived from the actual order, rather than generating a raw number. Enumeration beats generation whenever the space is closed.
- If the extracted amount is a *partial* refund, require a human (agent) confirmation step before the call fires — refunds are irreversible and outward-facing, so they sit on the "confirm" rung, not the "execute freely" rung.

**Double refund**
- This is hazard-class: agent/network retries duplicate an effectful call. Prompting "never refund twice" can't fix a retry that never routed back through the model's memory of what it already did.
- Add an idempotency key on the refund call — deterministic, derived from `order_id` (+ dispute/ticket ID if partial refunds are legit more than once), not from the model. Back it with a unique constraint in your refund table so a second request with the same key is a no-op, not a race.
- Separately, check current refund state before calling: if `order.refund_status != none`, don't call the tool at all — this belongs in your code, not in the model's judgment.

**Also worth doing before you ship the next version**
- Turn both production incidents into eval cases (bad-amount input, duplicate-request replay) and run them in CI on every prompt/model change — that's your only regression gate on something you can't unit test.
- Cap cost/steps per conversation so a stuck loop can't retry its way into a third duplicate refund.

Net effect: the model can still *misread* the chat, but it can no longer cause a wrong or duplicate charge — the schema, the server-side bound check, and the idempotency key make those outcomes unrepresentable rather than just discouraged. What's still possible on purpose: the model can propose a wrong reason/category (low stakes, easy to correct), and a legitimate second partial refund on the same order still goes through since idempotency keys aren't order-wide.

If you want, share the actual tool-call code and I'll implement the schema + idempotency key directly instead of describing it.