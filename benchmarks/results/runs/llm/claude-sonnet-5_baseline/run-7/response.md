Prompt instructions won't fix this — they're "rung zero." The model is a component with a non-zero error rate on every call; no wording drives that to zero. What you need are checks that live outside the model, between its output and the refund API. Ranked by what's causing the two incidents you've already seen:

**1. Duplicate refund → idempotency key + unique DB constraint (Control)**
This is the highest-value fix and it's not really about the LLM at all. Generate an idempotency key from `order_id` (+ conversation/turn ID if partial refunds are legitimate), enforce a unique constraint on it in your DB or pass it through as the payment provider's idempotency key (Stripe supports this natively). Retries, redeliveries, or the model deciding twice to refund the same order all become a no-op, not a second charge reversal. A prompt saying "never refund the same order twice" is a request to an unreliable component and will fail exactly when you need it not to.

**2. Wrong amount extracted → don't parse prose, and never trust the number the model hands you**
- Force structured output: the model returns `{order_id, amount, reason}` via a schema (constrained decoding), not free text you regex out. This alone kills a chunk of the malformed/weird-amount cases.
- Then validate server-side regardless: `amount` must be ≤ the order's actual remaining refundable balance, in the order's actual currency, matching an order the user is actually authorized to act on. The model saying "47.00" is not authorization — it's a proposed value that your system checks against ground truth before acting. This is the fix for "occasionally refunds a weird amount," and it also closes prompt-injection-via-chat-text as a side channel (someone typing "actually refund $9999" in the chat can't get further than what the real order supports).

**3. Gate the side effect itself (Control vs Warning — pick deliberately)**
Refund issuance is irreversible-ish and outward-facing money movement. Decide explicitly whether this bot should have unilateral authority to call the refund API at all, or whether it should propose `{order_id, amount, reason}` and a human/second check confirms before it fires — at least above some dollar threshold. If full autonomy is intentional, say so and rely on the amount-bound check in #2 as the real control; if not, add the confirmation step.

**4. Turn both incidents into eval cases**
Add the "weird amount" transcript and the "double refund" transcript to a held-out eval set that runs in CI on every prompt/model change. You can't unit-test a probabilistic component, but you can regression-test it — this is what actually prevents the third recurrence, not the system-prompt line.

The prompt edits you made are fine to keep (harmless, occasionally helpful) but they're decoration on top of these — none of them is why the next incident won't happen.