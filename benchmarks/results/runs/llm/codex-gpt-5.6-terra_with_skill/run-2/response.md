Yes. Those prompt lines are useful reminders, but they’re **rung 0**: the model can still be wrong. Don’t let it directly authorize a refund.

| Failure | Enforced device | Rung |
|---|---|---|
| Weird amount | Treat the model’s amount as an untrusted proposal. Server-side, derive allowed amounts from the order’s captured amount, prior refunds, currency, and line items; reject anything outside the remaining refundable balance. Store money as integer minor units/decimal, never float. | Control |
| Same refund twice | Require an idempotency key for every refund request and enforce a database unique constraint on `(order_id, idempotency_key)`. Bind the key to a hash of the requested amount/reason and replay the original result on retry; reject reuse with different parameters. | Control |
| Multiple partial refunds exceed the charge | Create the refund ledger entry and reserve/update the remaining refundable balance atomically in one transaction. | Control |
| Refunds without an eligible order | The bot should emit only structured fields—`order_id`, reason enum, requested amount/currency, confidence—not prose. The backend revalidates ownership, refund policy, order state, and currency before calling the provider. | Control |
| Model misreads ambiguous chat | Have it create a **pending refund intent**, then require a human confirmation showing customer, order, exact amount/currency, and reason before execution. For now, I’d turn off unattended refund execution. | Control on the bot; warning for the approver |
| Regressions | Add the production examples to a held-out eval suite, plus tests that deliberately submit an over-limit amount, a duplicate key, and a reused key with changed parameters—and prove each is refused. | Detection |

One important business-rule choice: if an order may only ever receive one refund, enforce `UNIQUE(order_id)`. If partial refunds are legitimate, don’t use that shortcut—use the idempotency key plus atomic remaining-balance guard instead.

Also keep the original customer message as evidence, but never let its text—or model-produced reason text—be a privileged instruction. Make refund reasons a closed enum where possible.

The core design is: **the model proposes; your refund service verifies and executes idempotently.**