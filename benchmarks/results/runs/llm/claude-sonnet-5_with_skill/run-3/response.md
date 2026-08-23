Short answer: the system-prompt additions are rung zero — they're asking an unreliable component to be reliable, and that's exactly why they didn't hold in production. The fix has to live outside the model, at the boundary between what the model says and what your refund API does.

**1. Wrong amounts — parse-don't-trust the extraction (Control)**
Right now you're presumably taking whatever number/reason the model produces and passing it to the refund API. Two separate devices needed:
- **Structured output**, not prose parsing: force the model to emit `{order_id, amount, reason}` against a schema (provider's structured-output mode), and validate the parsed result yourself. This kills malformed/ambiguous extraction, not just "weird" values.
- **Server-side bounds check**: the refund endpoint must independently look up the order and cap `amount` at what's actually refundable on that order. The model saying `amount: 500` is not authorization — it's a claim. `refund(order_id, amount)` should clamp/reject, never trust the caller's number. This is the same rule as any untrusted client input.

**2. Duplicate refunds — idempotency key + unique constraint (Control)**
"Never refund the same order twice" in the prompt can't survive a retry, a redelivered message, or the user re-pasting their complaint. The device: every refund call carries an idempotency key (e.g., derived from order ID, or order ID + a hash of the request), enforced by a **unique constraint in the database**, not application logic checking "have I seen this before" (that's a TOCTOU race under concurrency). Second call with the same key is a no-op that returns the first result.

**3. Refunds are irreversible — gate them (Control/Warning depending on budget)**
A refund is exactly the kind of side effect this mode calls out: the model should *propose*, not dispose. At minimum, cap what the model can trigger unattended (e.g., auto-approve under some threshold, require human confirmation above it) — same amount/order shown explicitly, not a generic "approve?" prompt.

**4. Turn both incidents into eval cases**
The wrong-amount case and the double-refund case are now regression tests, not anecdotes. Add them to a held-out eval set that runs in CI before any prompt/model change ships — otherwise you'll rediscover both bugs the next time someone "improves" the prompt.

**5. Pin the model version** if you aren't already — a silent provider-side model update is an unannounced deploy of the component causing your incidents.

The prompt wording is fine to keep as a first line of defense (rung 0 that costs nothing), but none of your actual fix should depend on it. Want me to draft the schema + idempotency-key implementation against your refund endpoint's current code?