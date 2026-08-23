Write permission was denied as well, so here it is in the conversation.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-22

**Scope**: 105 lines, one file. The detector (`detect_hazards.py`) never ran — Bash and sandbox exec were both denied — so this is the three lenses applied by hand.

One thing first: the file's own header says it's a deliberately hazard-rich eval fixture. The findings are real either way, but "been through review already" likely doesn't describe this file.

**Verdict**: `handleWebhook` turns an unsigned, unparsed body straight into a Stripe charge. Anyone who can reach that endpoint can move money. Everything else waits.

### 1. Unauthenticated charges via webhook — `:93`
No `stripe.webhooks.constructEvent`, no schema. `event.data.customer` and `.amount` are attacker-chosen. **Today: None.** → Verify the signature over the raw `Buffer` (not a re-serialized string) and zod-parse before any branching. **Control.**

### 2. Transfer destroys money — `:17-35`
`to` is fetched at line 19; if the account is gone, the debit at 25 commits and *then* `to!.balance` throws. No transaction. Money leaves and arrives nowhere. **Today: None** — the `!` suppresses the one warning available. → One `$transaction`, `findUniqueOrThrow`, and a conditional decrement (`where: { balance: { gte: amount } }`) that also closes the check-then-act race at 21-28 where two concurrent transfers both pass the balance check. Add `CHECK (balance >= 0)`. **Control.**

### 3. Negative amount reverses the transfer — `:17`
`transfer(attacker, victim, -1000)`: `balance < -1000` is false, so the guard passes, the debit subtracts a negative and the credit adds one. Money flows backwards, silently. → A `Money` constructor rejecting non-positive/non-integer, so it can't be expressed. **Control.** (A one-line `if (amount <= 0) throw` today is **Warning** and nearly free.)

### 4. Retry re-charges, no idempotency key — `:55-58`
A Stripe *timeout* is the bad case: the charge succeeded, the response was lost, the catch retries. Classic double charge. An optional `retry` boolean is rung zero. → **Required** `idempotencyKey` param derived from the caller's unit of work (invoice ID), plus `UNIQUE (customer_id, idempotency_key)`. Reserve it in the same transaction as the effect and replay the stored result — a caller that gets a constraint violation still doesn't know if the first attempt worked. **Control.**

### 5. `purgeCanceledAccounts()` deletes everything — `:80-91`
No argument → `olderThan || new Date()` → cutoff is *now* → the whole canceled population, via raw `DELETE`, uncapped, irreversible. The separate `findMany` also means the returned count isn't the deleted count. → Required cutoff, `maxRows` cap, dry-run default, delete by ID list. **Control.**

### 6. Failed charge returns `null` — `:59`
Collapses declined / timed-out / Stripe-down into one value. The timeout case may have charged the customer; `null` says it didn't. → Discriminated union with `{ status: "unknown" }` named, so the compiler won't let a caller read `.charge` without narrowing. **Control.**

### 7. Stringly-typed status, non-exhaustive switch — `:67-78`
`"cancelled"` (British spelling) writes successfully, matches no branch, and the customer keeps every paid feature forever. Silent. → Literal union + `assertNever` default. **Control.** Doesn't fix two neighbours: the write and the entitlement call aren't in a transaction, and nothing rejects `canceled → active`.

### 8. `applyDiscount` unbounded — `:63`
`150` returns a negative price; `0.2` meant as 20% gives 0.2% off and looks almost right, so it ships. Float money compounds it. → `Percent` parse 0–100, integer cents. **Control.**

### 9. Swappable `from`/`to` — `:17`
Two adjacent strings; reversed arguments compile and pass review. `id` and `ownerId` are both `string` too. → Branded `AccountId`/`OwnerId`. **Control.** (`type X = string` buys nothing — TS is structural.)

**Set aside** (5): `void sendReceiptEmail` fire-and-forget; positional `sendReceipt`/`retry` booleans; `currency = "usd"` default charging EUR invoices in USD; unused `WEBHOOK_TIMEOUT` read; `Account.status: string`. Lower blast radius, and most vanish as side effects of the above.

**Prerequisite**: every Control device here assumes `strict: true` and `tsc --noEmit` as a required CI check. Without that they're comments.

---

Two things I need from you before touching code:

1. **Is `strict` on with a required `tsc` gate?** That decides whether this list is devices or documentation.
2. **The legal subscription transitions are a domain call I shouldn't guess at.** #7 gives you the exhaustiveness check, but the transition rules (can `canceled` → `active` on reactivation? does `past_due` → `canceled` need a dunning window?) are yours. If you sketch the allowed pairs, I'll build the single transition function that makes everything else unrepresentable.

Say which findings you want applied and I'll do them with `poka-yoke:` markers naming the mistake each one blocks.