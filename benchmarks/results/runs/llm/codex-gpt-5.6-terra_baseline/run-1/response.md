Yes: move those rules out of the prompt and into the refund system itself. Prompts are useful for extraction, but they aren’t a reliable control for moving money.

- Treat the model output as an untrusted refund *request*, not an API command. Extract structured fields: `order_id`, `amount_minor`, `currency`, `reason`, and confidence/evidence.
- Resolve the order server-side; never let the model invent the amount or currency. Validate the requested amount is positive, matches the order’s currency, and is ≤ remaining refundable balance.
- Use integer minor units (`1299`, not `12.99`) to avoid decimal/currency errors.
- Enforce duplicate prevention in the refund service/database: a unique refund operation keyed by order/payment plus a stable idempotency key. Make the check-and-create atomic, and pass the same key to the payment provider.
- Require a clear order match. If multiple orders or amounts appear, or the amount differs from the eligible balance, route to review rather than guessing.
- Use policy thresholds: auto-refund only low-risk cases; require human approval for large amounts, partial refunds, ambiguous messages, or repeat requests.
- Log the customer text, extracted fields, resolved order, validation results, idempotency key, API result, and model/version—then alert on anomalies.
- Test the controls by deliberately sending malformed amounts, conflicting currencies, concurrent duplicate requests, retries/timeouts, and messages with multiple orders.

The critical property is: even if the model outputs `$9,999` twice, your refund API layer must be incapable of issuing an invalid or duplicate refund.