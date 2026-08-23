Yes: move those guarantees out of the prompt and into the refund system.

- Have the model return a structured *refund request*, not call the API directly: `order_id`, `amount_minor` (integer cents), `currency`, `reason`, and perhaps the source message span/confidence.
- Server-side, look up the order and validate:
  - order exists and belongs to that customer
  - currency matches
  - amount is positive, within the paid/refundable balance, and follows your partial-refund policy
  - no float arithmetic—use integer minor units or a money type
- Make the refund endpoint idempotent. Require an idempotency key derived from the order plus the customer’s actual refund request/event ID; persist it with a unique database constraint. A retry or duplicate bot call must return the original refund result, not issue another refund.
- Require explicit confirmation for ambiguous messages, unusual amounts, or refunds above a threshold. Show the resolved order and amount before execution.
- Record an audit trail: original message, extracted fields, validation decision, idempotency key, provider refund ID, and actor/model version.
- Test the failure cases deliberately: “refund $12.50, not $125,” multiple amounts in one message, currency symbols, prior partial refunds, retries/timeouts, and two concurrent requests for the same order.

The prompt can improve extraction quality, but it cannot guarantee money correctness or uniqueness. Your refund API/database must make an invalid or duplicate refund impossible.