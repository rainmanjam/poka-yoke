Loaded `poka-yoke:llm` (AI features shipped to users) since this is a refund tool-call from an untrusted chat message — not a repo-hazard case. Your two prompt additions are rung zero: "be careful" and "never twice" are training a component that can't be trained reliably. Here's the audit, ranked by blast radius:

## 1. Amount is parsed from model prose — money/high, silent
**Mistake**: model free-generates the refund amount from chat text; anything it gets wrong looks like a normal API call.
**Consequence**: wrong amount refunded, silently — no error, just a number nobody re-checked.
**Today**: None (a prompt instruction isn't a device).
**Device → Control**: two changes, both required:
- Structured tool-call schema, not prose parsing: `refund(order_id: str, amount: Decimal, reason: Literal[...])`, validated against the schema before anything fires.
- Server-side re-derivation: don't trust the model's `amount` as authorization. Look up the order, cap `amount` at what was actually charged (or a configured refundable ceiling), and reject/flag anything the model proposes that exceeds it. The model proposes; your code disposes.

## 2. No idempotency key on the refund call — money/high, silent
**Mistake**: agent retries (timeout, redelivered message, user re-pastes the same complaint) and calls `refund()` twice for the same order.
**Consequence**: double refund, silent — "never do X twice" in a system prompt does not survive a retry, because a retry isn't the model deciding to refund again, it's your orchestration replaying the same intent.
**Today**: None.
**Device → Control**: generate an idempotency key from `(order_id, refund_intent)` and enforce it with a **unique constraint** on the refund API/DB side, not just an app-level check-then-act (that's a TOCTOU race under concurrent retries). This is the highest-leverage single change here.

## 3. No confirmation gate before an irreversible financial action
**Mistake**: bot fires the refund the moment it decides to, with no human or customer confirmation step.
**Consequence**: any of the above failures ships immediately instead of pausing.
**Device → Warning/Control**: require a confirmation turn that echoes back the exact order ID + amount before calling the tool, and/or route anything above a $ threshold to human approval. Cheap, and catches cases the schema/cap don't.

## 4. Reason field is free text
Lower stakes, but if it's used for anything downstream (routing, reporting), enumerate a fixed set of reason codes instead of letting the model generate strings — closed sets can't drift.

## 5. No eval for this failure class
The two production incidents (wrong amount, double refund) should become permanent eval cases run in CI on every prompt/model change — otherwise you won't know if a future prompt tweak reintroduces either.

**Bottom line**: keep the prompt wording if you like, but it's decoration. The load-bearing fixes are (2) the idempotency unique-constraint and (1) the server-side amount cap — both live in code the model never touches, which is why they can't be re-broken by a prompt edit six months from now.