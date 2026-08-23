**Subject: Refund bot extraction and deduplication** — applying the method directly.

The system prompt is rung 0 (training). It won't work because:
- **Extraction**: The LLM is doing its best to parse freeform chat, and "be careful" doesn't make extraction more accurate or bounded.
- **Deduplication**: A duplicate refund is a concurrency + retry problem that lives below the bot's layer. The LLM can't see what already happened in the database.

Here's what you actually need:

---

## Hazard 1: Wrong refund amount extracted

**The mistake:** LLM extracts `$50` when the customer said "refund $5000" or "$0.50", or hallucinates an amount that wasn't there.

**What happens:** Refund is too small (customer angry), too large (revenue loss), or nonsensical (customer confused about what happened).

**Is it silent?** Yes — the bot happily calls the API with a plausible-looking number.

---

**Device: Contact (rung 1) — lookup + validation**

Before calling the refund API, the bot must:
1. Extract the order ID from the chat (required, not optional)
2. Look up the order from your database
3. Validate the extracted amount against the order total: `extracted_amount <= order.total_amount`
4. Reject refunds that don't fit (throw, don't retry with prompting)

**Why this is rung 1:** The API will not execute a refund for an order ID with no matching order or for an amount larger than the order. The extraction error cannot become a refund — the type system (order exists + amount is in-bounds) makes it impossible.

**Alternative (rung 2 if lookup is hard):** The refund API validates and rejects, but you lose the ability to fast-fail in the bot.

---

## Hazard 2: Same order refunded twice

**The mistake:** Bot receives two support messages for the same order (customer follows up, message arrives twice, etc.), or bot retries the API call after a transient error, and both complete successfully.

**What happens:** Customer is refunded twice; you eat the revenue loss, or the second refund fails and customer loses trust.

**Is it silent?** Yes — nothing stops the second call from happening.

---

**Device: Motion-step + fixed-value (rung 1) — idempotency key**

The refund API must accept an `idempotency_key` parameter:
- The bot generates it as a deterministic hash: `idempotency_key = hash(order_id + reason + amount)`
- The API stores the key alongside each refund in the database
- On the second call with the same key, the API returns the *same* refund record without re-applying
- Database constraint: `UNIQUE(idempotency_key)` ensures only one refund per key ever reaches the ledger

**Why this is rung 1:** The second refund is physically impossible because the database constraint + idempotency check make it unrepresentable. The bot can retry as many times as it wants; only one refund ever executes.

**Why not just check the database first?** That's rung 2 (warning) — you check if the order was already refunded, and reject if so. But that has a TOCTOU race: between the check and the refund, another request can slip through. Idempotency keys are rung 1 because the database constraint prevents the race.

---

## Summary

| Problem | Today | Fix | Rung |
|---------|-------|-----|-----|
| Wrong amount | System prompt instruction | Order lookup + validation in bot, or validation in API | 1 |
| Duplicate refund | System prompt instruction | Idempotency keys + DB constraint in API | 1 |

Both belong in the **data layer and API contract**, not the LLM prompt. The bot's only job is to extract cleanly and pass an idempotency key. The API is responsible for catching bad amounts and preventing duplicates—because those are guarantees your customers need, regardless of who is calling the refund endpoint (support bot, admin dashboard, Stripe webhook, etc.).