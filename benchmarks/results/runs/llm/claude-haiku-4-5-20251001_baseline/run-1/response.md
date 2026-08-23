System prompt instructions won't solve either problem — they degrade at runtime, and the failures are architectural, not instructional.

**Weird amounts** need **structured extraction + validation**, not better prompting:
- Extract via a schema (Zod, Pydantic) that enforces type/format — catches `$50` vs `$5.00` extraction errors the LLM makes
- Validate against the order: confirm extracted amount ≤ order total, matches expected currency, passes sanity checks
- These checks run before the API call, every time, deterministically

**Duplicate refunds** need **idempotency**, not a reminder:
- Give every refund request a unique idempotency key (order ID + timestamp, or a request ID from the chat context)
- Database query before calling the API: has this order been refunded in the last [N] minutes? If yes, return the cached response
- If your refund API supports idempotency keys, use them — calling twice with the same key only refunds once (API-level guard)

The pattern: **move safety from prompts into code**. A database check that prevents duplicate refunds will always work. A system prompt note won't.

What's your refund API's current interface — does it already support idempotency keys, or do you need to add a deduplication layer in your bot's caller?