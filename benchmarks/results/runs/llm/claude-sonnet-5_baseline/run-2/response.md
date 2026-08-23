Two prompt lines won't fix this — both bugs are exactly what happens when an unreliable component's output is trusted directly. Here's what's actually happening and what closes each gap:

**1. Wrong amounts — you're parsing prose instead of enforcing structure**
- *Mistake:* Free-text extraction from chat means the model can misread "$50" as 500, misplace a decimal, or grab the wrong number if the message mentions several.
- *Consequence:* A refund for an amount nobody actually asked for.
- *Device:* Use structured/tool-calling output with a schema (amount as a bounded number, order_id required, reason as an enum, not free text). Then, critically, **validate server-side against the actual order** — the refund amount must be ≤ what was actually paid on that order_id, checked in your backend, not trusted from the model's output. "Be careful extracting the amount" is a request to an unreliable component; a range check against the real order is a device.

**2. Double refunds — no idempotency key**
- *Mistake:* Nothing stops the same logical action from executing twice — a retry, a re-run, or the model deciding twice in one conversation all look like fresh calls.
- *Consequence:* Same order refunded twice, real money out the door.
- *Device:* Generate an idempotency key per refund attempt (order_id + amount, or a key from the triggering message) and enforce it with a **unique constraint at the database/API layer**, not just an in-conversation check. "Never refund the same order twice" in the prompt is exactly the comment-not-device pattern this keeps happening with — the model can't reliably remember state across a session, and it shouldn't have to.

**3. The bigger gap: nothing gates the side effect itself**
- Refunds are irreversible and outward-facing (real money, real Stripe/bank call). Right now the model's decision goes straight to the refund API. Add:
  - A cap on refund amount the bot can issue autonomously (anything above, say, $50 or above the original charge, requires human approval).
  - A tight tool schema — `refund(order_id: str, amount: float, reason: Literal[...])` with no free-text field the model can smuggle extra context through.
  - Logging of every extraction (raw message → parsed amount/reason → validation result) so misfires are visible instead of silent.

**4. Close the loop**
Every production incident you've had (wrong amount, double refund) should become a permanent eval case that runs in CI before any prompt/model change ships. That's what actually prevents recurrence — the prompt fix stops this one instance, the eval stops the next model update from reintroducing it.

Want me to look at the actual extraction/refund-call code and point to the specific lines to change?