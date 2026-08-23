## Goal Description
The support bot is currently using prompt instructions ("be careful to extract the exact amount", "never refund the same order twice") to prevent incorrect refund amounts and duplicate refunds. In the poka-yoke framework, **prompt instructions are "rung zero" (training)**. They are requests to an unreliable component and will inevitably degrade. 

To fix this properly, we need to build "devices" outside the model that constrain what its output can reach. The model acts as an untrusted client: it proposes the action, but the system must dispose of it safely.

## User Review Required
> [!IMPORTANT]
> The proposed devices require changes to your backend `refund API` rather than the bot's code. Please confirm if you have the ability to modify the API, or if we need to implement these devices as an intermediate proxy layer between the bot and the external API.

## Open Questions
> [!WARNING]
> - **Refund amounts:** Does the bot ever need to issue *partial* refunds, or is it always a full refund? If it's always a full refund, the best device is to remove the `amount` parameter entirely from the bot's tool schema and let the backend handle the math.
> - **Idempotency:** Does your current refund API support passing an `idempotency_key` header or parameter?

## Proposed Changes

### 1. The Idempotency Device (Fixing Double Refunds)
Agent loops often retry on network timeouts or transient errors, which leads to duplicate tool calls. A system prompt cannot prevent this. We must implement a **Control-rung (Motion-step) device** to make duplicate refunds impossible.

#### [MODIFY] Refund API / Bot Tool Schema
- **Add an Idempotency Key:** The bot's tool schema should either automatically inject an idempotency key (e.g., `refund_{order_id}`) or the API should enforce that an order can only transition to a `refunded` state once. 
- **Database Constraint:** Ensure your backend has a unique constraint on the refund action for a given order, so a second request safely returns a `200 OK` (or `409 Conflict`) without moving any money.

### 2. The Validation Device (Fixing Weird Amounts)
The model is an untrusted client; its input is not authorization. We must implement a **Control-rung (Contact) device** to ensure invalid amounts cannot fit through the interface.

#### [MODIFY] Refund API
- **Server-Side Bounds Checking:** The `refund(amount)` API must independently fetch the original order total and reject any request where `amount > order_total`.
- **Structured Output:** Ensure the bot uses a strict structured output schema (e.g. JSON Schema via constrained decoding) for the refund amount, rather than regex parsing prose. Use a strongly typed `float` or integer cents to prevent formatting errors.

## Verification Plan

### Automated Tests
- Write a test that calls the Refund API twice for the same order ID and assert that the second call results in a no-op or is safely rejected.
- Write a test that attempts to refund `order_total + 0.01` and assert that the API rejects the request.

### Manual Verification
- Remove the "be careful" and "never refund twice" instructions from the prompt (they are no longer needed).
- Force the bot to attempt a double-refund and verify the system catches it gracefully.
- Force the bot to attempt an over-refund and verify the API blocks it.