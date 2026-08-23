Short answer: the two prompt additions you made are rung zero — they're instructions to an unreliable component, not devices. They'll reduce the failure rate a little and then stop mattering, because nothing outside the model is actually checking anything. Here's what would close each hole for real.

**1. Wrong amount extracted → stop parsing prose, extract via structured/tool output**
Consequence: any regex/prose-parse of "refund me $150" can silently produce `$1500`, `$15`, or grab the wrong number if the message mentions two amounts.
Device: have the model call a `propose_refund(order_id, amount_cents, reason)` tool with a schema (amount as an integer in cents, not a free-form string), validated against that schema. This doesn't make the amount *correct*, just well-formed — the next device does that.

**2. Model-proposed amount used directly → validate server-side against the order**
Consequence: even a well-formed amount is just a client claim. The model saying `9999` isn't authorization.
Device: before refunding, look up the order and clamp/reject: amount must be ≤ (amount actually paid − amount already refunded). Reject anything else outright — don't silently cap it, since a silent cap can also mask a bug.

**3. Same order refunded twice → idempotency key, not a prompt rule**
Consequence: "never refund the same order twice" is a request; it doesn't survive a retry, a duplicate webhook, or the user saying "refund me" twice in one conversation.
Device: idempotency key = order ID (or order ID + attempt) on the refund call, backed by a **unique constraint** in the DB/at the payment processor, not just an app-level check (that's a TOCTOU race, same pattern as your earlier double-charge incident).

**4. Refund is irreversible money movement → gate it**
Device: for refunds over some threshold (or all of them, if volume allows), require explicit confirmation — either a human-in-the-loop step or at minimum an echo-back-and-confirm turn ("Refunding $150 to order #4821 — confirm?") that the *system*, not the model, decides is required before calling the tool.

**5. No detection layer → turn these two incidents into eval cases**
You now have two known failure modes (wrong amount, duplicate refund). Add them as eval cases with assertions on the structured fields (amount_cents, order_id, idempotency behavior) and run in CI on any prompt/model change — otherwise you won't know if a future prompt tweak reintroduces either bug.

Priority order if you can only do two things this week: **#2 (server-side amount validation) and #3 (idempotency key + unique constraint)** — those are the ones that actually stop money moving incorrectly, independent of what the model does.