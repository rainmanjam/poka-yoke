System prompts can't enforce behavior—they're just suggestions. Your two issues need application-level devices, not training:

**For weird amounts:**
- Parse and validate on the backend before calling the refund API. Reject amounts outside expected ranges or in unexpected formats. Don't trust extraction.
- Log what the bot extracted vs. what the API received—if they diverge, you have a parsing problem.

**For duplicate refunds:**
- Use **idempotency keys** (order ID + timestamp or a request ID) in your refund API calls. Your backend should deduplicate: if the same idempotency key is seen twice, return the cached result instead of refunding again.
- Add a **unique constraint** in the database (`UNIQUE(order_id, refund_timestamp)` or similar) so duplicate writes fail at the database layer, not just at the application layer.
- This also protects against retries, network hangs, and the bot processing the same message twice.

**Add observability:**
- Log every refund with: extracted amount, validated amount, order ID, idempotency key, final result.
- Alert on: amount validation failures, duplicate idempotency key attempts, refunds outside thresholds.

**Consider a human gate:**
- For refunds over a threshold, route to a human approval step instead of auto-executing.

The pattern: validation on ingestion + idempotency + deduplication at storage. These are devices that *fail loudly* when something goes wrong, not instructions that degraded over time.