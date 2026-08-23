I've read the router, the `llm` sub-skill, and the two catalog hazards it cites (M2, F7). Here's the answer in the skill's audit voice.

## Short answer

The two system-prompt lines you added are **rung zero** — they're requests to a component with a non-zero error rate on every call. They'll reduce the frequency a little and they won't stop either failure. Both of your bugs have a proper *device*: something outside the model that makes the mistake impossible or self-announcing. Here they are, ranked.

## 1. Double refund → required idempotency key, enforced by the database (Control)

**Mistake:** The model (or a retry in your agent loop, or a customer who re-sends the message) calls `refund(order_id, …)` twice. This is hazard M2 — at-least-once delivery plus an effectful call with no key — and an LLM loop retries far more than any human path.

**Device:** Make the refund API *require* an idempotency key, derived deterministically — e.g. `sha256(order_id + ticket_id)` or simply `order_id` if one refund per order is the business rule — and back it with a `UNIQUE (order_id, idempotency_key)` constraint, reserved **in the same transaction** as the refund. The second call then fails at the DB, not at the model's discretion. If the key is optional, it's rung zero in costume.

## 2. Weird amount → stop generating it, validate it server-side (Control)

**Mistake:** The model extracts `$149.99` from "I paid $49.99, and my friend paid $149.99", or invents a number, and the API trusts it.

**Devices, stacked:**
- **Enumerate, don't generate.** Look the order up *before* the call and hand the model the order's actual line items/total as a closed list. It picks a line-item ID or `full_order`; it never types a dollar figure. A model choosing among five IDs can't invent a sixth.
- **Server-side check regardless.** `refund(amount)` must re-verify `amount <= order.total - already_refunded` against the order record. The model saying `9999` is not authorization.
- **Structured output with a tight schema** — `amount: Decimal(ge=0)`, `reason: Literal[...]` from your reason codes, `extra="forbid"` — so parse failures and invented reason strings become schema errors instead of API calls.

## 3. Gate the irreversible action (Control)

Refunds are outward-facing money. Split tools by reversibility: reads execute freely; `issue_refund` above some threshold (or all of them, initially) queues a confirmation that names the exact order and amount for a human or a deterministic policy check. The model proposes; the system disposes.

## 4. Every production failure becomes an eval case (Detection)

You have at least two real failures. Put the exact chat messages into a held-out eval set that asserts on the structured fields, run it in CI on every prompt/model change, and **pin the model version** — a provider update is an unannounced deploy of your least predictable component. Without this, you can't tell whether your prompt edits helped or just moved the noise around.

## Rung summary

| Failure | What you did | Rung | Device | Rung |
|---|---|---|---|---|
| Double refund | "never refund twice" in prompt | 0 | Required idempotency key + unique constraint | Control |
| Wrong amount | "extract the exact amount" in prompt | 0 | Closed-set choice + server-side amount check + schema | Control |
| Either | — | — | Confirmation gate on money | Control |
| Regression | — | — | Eval set in CI, pinned model | Detection |

Keep the prompt lines — they're harmless — but the finish line is the unique constraint and the server-side amount check. If you paste the refund handler and the tool schema, I'll propose the concrete diff (per the skill, I'll show it before editing).