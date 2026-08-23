The two prompt lines you added are rung zero — they make the model *more likely* to behave, but they don't change what's possible when it doesn't. Both of your production incidents are structural gaps, not phrasing gaps:

**1. Duplicate refunds → missing idempotency key (Control)**
"Never refund the same order twice" is a request to a component with a non-zero error rate. The device: generate (or require) an idempotency key per refund request — e.g. `hash(order_id + amount + reason)` or a client-generated request ID — and enforce a unique constraint in your DB or pass it straight through as the Stripe/payment-provider idempotency key. Retries, double-sends, or two chat turns both triggering a refund action all collapse to one actual charge. This alone would have prevented both duplicate incidents regardless of what the model decided.

**2. Wrong amounts → prose parsing instead of structured + validated output (Control)**
If the bot is extracting amount/reason from free text into a string or a loosely-typed field, that's the failure mode. Two changes:
- Use structured/constrained output (a schema: `amount: float`, `reason: enum[...]`, `order_id: string`) so malformed shapes are rejected before they reach your code.
- **Never trust the extracted amount as authorization.** Validate it server-side against the actual order: refund amount must be ≤ the order's paid amount (or remaining refundable balance). The model saying "$400" isn't proof the order was $400 — check.

**3. No reversibility gate on an irreversible action**
A refund is money leaving the business; it belongs on the "requires confirmation" side of the reversibility line, not auto-executed from a chat inference. At minimum: amounts above some threshold (or all of them, if volume allows) get a human-in-the-loop confirmation step that names the exact order, amount, and reason before the API call fires. This also gives you a place to catch "weird amount" cases — a $9,999 refund on a $40 order looks obviously wrong to a human in a way it doesn't to a model mid-generation.

**4. No regression coverage**
Both of these production incidents should become permanent eval cases (duplicate-request replay, malformed/injected amount extraction) run in CI before any prompt or model change ships — otherwise you have no way to know if a future prompt tweak reopens either hole.

What this leaves possible on purpose: the model still decides *what* refund to propose from the conversation — that's the right place for it. What it can no longer do is make that proposal *become money* without a server-side check on amount, a dedup key, and (depending on volume) a human confirming it.

Want me to sketch the actual endpoint (idempotency key + amount validation + confirmation gate) in your stack?