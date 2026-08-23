Short answer: the two prompt additions don't fix anything, because instructions are the *least* reliable layer you have — they're a request to a component with a non-zero error rate, not a constraint on it. Both incidents you saw map to specific missing devices, not missing wording.

**1. "Refunded a weird amount" → you're trusting parsed prose as authorization**

If the bot is extracting an amount from free text and passing it straight to the refund call, "be careful to extract the exact amount" doesn't change the failure mode — it just makes it slightly less likely per call, forever.

- Use structured/constrained output for the extraction (schema: `amount: float`, `reason: enum|string`, `order_id: string`), not prompt-and-parse.
- Never treat the extracted amount as ground truth. Before calling the refund API, validate it server-side against the actual order: `amount <= order.amount_paid - order.already_refunded`. The model saying `$400` is not authorization for `$400` — it's a proposed value that your code checks.
- If the amount exceeds some threshold (or just: any amount, your call), require a confirmation step naming the exact order and amount before the refund fires. Refunds are irreversible-ish and outward-facing — that's the class of action that needs a gate, not a reminder.

**2. "Refunded the same order twice" → this is a missing idempotency key, not a missing rule**

"Never refund the same order twice" is unenforceable by prompt because the failure isn't the model *deciding* to double-refund — it's almost certainly a retry (agent loop retry, timeout-and-resend, user re-sending a similar message) hitting the tool call again. A "check if already refunded" lookup-then-act has a race window (TOCTOU) even if you added it.

- Generate an idempotency key from the order ID (+ maybe a refund-request ID) and pass it to the refund API/DB call, backed by a unique constraint. Second call with the same key is a no-op or returns the original result, structurally, not by the model remembering not to.

**3. Close the loop so this doesn't recur silently**

- Turn both production incidents into eval cases (the exact transcripts that caused them) and run that eval set in CI on any prompt/model change. Without this, you won't know if a future prompt tweak reopens either hole.
- Pin the model version — an unannounced model update is an unannounced deploy of the component that's already causing you the most trouble.

If you want, I can look at the actual extraction/tool-call code and point to the specific lines where the schema and idempotency key should go — right now I'm going off your description, not the implementation.