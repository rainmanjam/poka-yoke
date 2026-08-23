Read the router, then `llm` (AI feature you ship to users) plus `retro` (double refund already happened) and the hazard catalog.

## The short version

Both lines you added to the system prompt are **rung zero**. They're requests to a component with a non-zero error rate on every call — they help a little, they never stop anything. "Never refund the same order twice" is especially hopeless: on a retry or a second conversation the model has no memory of the first refund, so it isn't disobeying, it genuinely doesn't know.

Every real device here sits **outside** the model.

## Ranked by blast radius

**1. The model is the source of truth for the amount.** It's reading "I paid like 47 or 48 bucks" and generating a number. Nothing downstream disagrees with it.

Device — stop generating, start enumerating. Fetch the order first, hand the model the refundable line items with IDs and their real amounts, and have it return *IDs from that list*. The server computes the money from the order. A model choosing among five IDs can't invent a sixth; a model asked for a number always eventually invents one. **Control.**

If you must keep a free amount field: integer minor units (never a float — 0.1 + 0.2 ≠ 0.3 and reconciliation dies), and a server-side `amount <= order.refundable_amount` check that rejects. The model saying `9999` is not authorization.

**2. Double refunds are hazard M2 — non-idempotent retryable effect.** Required idempotency key derived from `(order_id, conversation_turn)`, backed by `UNIQUE (order_id, idempotency_key)`. Two subtleties that catch people: the key must be reserved *in the same transaction as the refund*, and the second caller must get the stored result replayed — a caller that retries and gets a constraint violation has learned nothing about whether the first attempt worked. An optional idempotency key is rung zero wearing a costume. **Control.**

Add the backstop too: `CHECK (refunded_total <= captured_total)` on the order. That catches partial-refund stacking, which your prompt line doesn't even address.

**3. The input is attacker-controlled.** A customer types the chat message that reaches a money-moving tool. The question isn't "can the model be tricked" (yes) but *what it can reach when it is*. Scope the refund credential to that customer's own orders rather than service-level, and cap it — per call, and per user per day.

**4. No confirmation gate on an irreversible action.** Split tools by reversibility: reads execute freely, refunds above a threshold go to a queue where a human sees the order and the amount. **Control** for the expensive tail.

**5. Tool schema is probably too wide.** `reason` should be a `Literal` set, not a free string; no "additional context" text field; `order_id` required; `extra="forbid"`.

**6. The failure path.** Malformed output, refusal, timeout, empty order lookup — is there a deterministic handoff to a human, or does something get defaulted? A silent default here is `except: pass` with a language model attached.

**7. You have no detection.** How did you learn about the weird amounts — a customer complaint? Then nothing is watching. A daily reconciliation of refunds issued against orders is rung 3 but it's the difference between hours and weeks. And your two production failures are your first two eval cases: build a held-out set, assert on the *structured fields*, run it in CI on every prompt change, and pin the model version so the provider can't deploy your least predictable component for you.

`★ Insight ─────────────────────────────────────`
The reason "works great in testing" is the tell: testing exercises the paths you imagined, and an LLM's error mode is the input you didn't imagine. That's why the ladder matters — a test covers the case you thought of, a `UNIQUE` constraint covers every case forever.
`─────────────────────────────────────────────────`

## The one decision that's yours

Where the human gate sits. Auto-approving everything under $20 and queueing the rest is a very different product from queueing everything — it trades support load against tail risk, and only you know your refund distribution and your fraud exposure. Tell me the ceiling (and your stack) and I'll write the tool schema, the idempotency layer, and the migration.

I haven't seen the code — these are the hazards to check for, not confirmed findings. Point me at the handler and I'll run the detector and give you a real audit against the actual call sites.