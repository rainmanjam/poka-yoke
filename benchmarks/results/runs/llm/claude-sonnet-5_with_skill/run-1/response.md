Loaded `poka-yoke:llm`. Its core point applies directly here: **the two lines you added to the system prompt are rung zero.** "Be careful with the amount" and "never refund twice" are instructions to a component that has a non-zero error rate on every call — no phrasing drives that to zero. They'll reduce frequency, not eliminate it, which is exactly what you're seeing: works in testing (few calls, no adversarial/edge inputs), fails in production (volume + retries + weird phrasing).

Here's what's actually happening and the devices that fix each, ranked by how strong a guarantee they give:

**1. Wrong amounts — you're trusting parsed prose as authorization.**
Mistake: the model's extracted number is being passed straight to the refund API as if it were verified. Any hallucination, misread ("refund my $50, the other charge was $230" → picks 230), or unit confusion becomes real money moved.
Device (Control, contact lens): stop letting the model assert the amount at all if you can help it. Look up the order server-side, compute the actual refundable amount (paid − already refunded), and either (a) have the model just confirm *which order*, with amount computed by your code, or (b) if the model must extract an amount, clamp it server-side to `[0, order.refundable_amount]` and reject anything outside that — the model's number is a suggestion, never ground truth. Use structured output (schema: `order_id`, `amount_cents: int`, `reason: enum`) instead of parsing prose, so malformed shapes are rejected before they even reach your validation.

**2. Duplicate refunds — no idempotency key.**
Mistake: nothing stops the same logical refund from being issued twice — whether from a model retry, an agent loop retry, or the user rephrasing the same request. "Never do it twice" in a prompt can't stop this; the model has no memory of what it already did across calls/retries.
Device (Control, motion-step): idempotency key on the refund call itself — derived deterministically from `order_id` (or `order_id + reason_hash`), passed to your payment processor's idempotency header (Stripe supports this natively), backed by a **unique constraint** in your own DB on refunds-per-order. This is the one that actually makes double-refund impossible, independent of what the model does.

**3. Reason field — enumerate, don't generate.**
If "reason" flows anywhere beyond a label (reporting, policy branching), constrain it to a closed set of IDs you supply, and have the model pick one rather than free-text. A model asked to invent a reason will eventually invent a wrong one; a model choosing among 6 IDs can't.

**4. Bound the blast radius.**
Cap max refund amount per call and require a human/second gate above some threshold — refunds are irreversible-ish (money out), so this is the same "irreversible action needs confirmation naming the exact amount" rule as any other side-effecting tool call.

**5. Turn the two incidents into eval cases.**
You can't unit test the model, but you can regression-test it: add both the "weird amount" transcript and a retry/duplicate scenario to a held-out eval set that runs in CI before any prompt/model change ships. That's the only thing that tells you a future prompt tweak didn't reopen this.

The honest rung count: (1) and (2) reach **Control** because they live outside the model (DB constraint, server-side clamp). Everything you can do *inside* the prompt stays **Warning at best** — worth keeping, but only as a second line behind the server-side checks, not a substitute for them.

Want me to look at the actual refund tool/handler code and wire in the amount-clamp and idempotency key?