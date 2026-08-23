A prompt is training, not a safeguard. Put the guarantees in the refund workflow itself.

- Extract into a strict schema: `{order_id, amount_minor, currency, reason_code, confidence}`. Use integer minor units (cents), never floating-point text.
- Validate against authoritative order data before calling the API: order exists, currency matches, amount is positive, and total refunded + requested amount ≤ paid amount.
- Make the operation idempotent. Generate a stable key such as `refund:{order_id}:{refund_request_id}` and enforce it both in your database (unique constraint) and at the refund API. Retrying the same request must return the original refund, not create another.
- Define whether partial/multiple refunds are allowed. If not, atomically lock/mark the order as refunded before submitting; if yes, use the cumulative-cap check above.
- Separate extraction from execution: have the model propose structured data, then deterministic code validates and submits it. If parsing is ambiguous, absent, or violates a rule, ask the customer or send it to review—don’t guess.
- Record the original customer message, extracted fields, validation result, idempotency key, and provider refund ID; alert on rejected/duplicate attempts.

The core invariant should be enforced atomically:

```text
refund_total(order) + requested_amount <= amount_paid(order)
AND idempotency_key has not been used
```

Only then create the refund. The model may help interpret language, but it should never be the component that guarantees monetary accuracy or uniqueness.