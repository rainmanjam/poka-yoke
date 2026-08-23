File write wasn't approved, so here it is in-conversation. Ranked by blast radius × ease of mistake.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-22

**Verdict:** `purgeCanceledAccounts()` with no argument deletes every canceled account that has ever existed — and returns a count from a different query than the one that deleted.

### 1. Purge's default is "delete everything" — irreversible loss / one forgotten arg
`payments.ts:80`. `olderThan || new Date()` makes the cutoff *now*, so `canceled_at < cutoff` matches every canceled row. The destructive default is the one you get by forgetting. Three compounding defects: raw interpolation into `$executeRawUnsafe`; `doomed.length` (line 82) counts a *different* query than the `DELETE` (line 86), so your logs can say 12 when it was 12,000; no transaction, no row cap. **Today: None.** → Make `olderThan` required, `deleteMany` by the exact IDs counted, inside `$transaction`, with a `maxRows` that throws when exceeded. **Control.**

### 2. Webhook moves money on unauthenticated input — security bypass + money / no mistake required
`payments.ts:93`. No signature check. `event.data.amount` goes straight into `chargeCustomer` as cents — anyone who learns the URL charges any customer any amount. Also non-idempotent, so Stripe's normal redelivery double-charges. `WEBHOOK_TIMEOUT` is read and never used — dead config that reads like a control. → `stripe.webhooks.constructEvent(rawBody, sig, secret)` **before** parsing (note: raw `Buffer`, not `string` — re-serializing breaks verification), then schema-parse the payload. **Control.**

### 3. `transfer` destroys money on the unhappy path — silent corruption / a missing account
`payments.ts:17`. The debit commits at line 25; `to!.balance` throws at line 31 if `to` is null. Money leaves and arrives nowhere. Same outcome for any crash between the two un-transacted updates. And the JS-side read-modify-write is a lost update under concurrency. → One `$transaction`, `findUniqueOrThrow`, and `{ decrement: amount }` in-DB with `where: { balance: { gte: amount } }`. Backstop with `CHECK (balance >= 0)`. **Control.**

### 4. Retry without an idempotency key — double charge / one timeout
`payments.ts:56`. Stripe can succeed and still throw locally; the retry creates a second real charge. → Required `idempotencyKey` in the signature + `UNIQUE (customer_id, idempotency_key)`. **Control.**

**5–8, briefly:** swappable adjacent args (`transfer(from, to)`, `applyDiscount(20, 100)` → free, two adjacent booleans) and no `amount > 0` check — negative amounts invert transfers and pass the funds check; `catch → return null` swallows declines *and* bugs so callers fulfill unpaid orders; `updateSubscription` persists any string then silently falls through its switch, leaving canceled users entitled; `balance: number` drifts and `transfer` never compares currencies.

`★ Insight ─────────────────────────────────────`
- Finding 1's real teacher is the count: `findMany` then a separate `DELETE` is the same TOCTOU shape as finding 3's balance read — *observe, then act on the assumption nothing moved*.
- Ranking crashes *below* silent wrong answers is why #3 outranks #5: a TypeError is loud; a ledger that quietly drifts compounds.
- Branded IDs are compile-time only — they vanish through `JSON.parse`, so they must be applied by a parse function at each boundary or they're decoration.
`─────────────────────────────────────────────────`

**Your call, and it shapes the fix:** for finding 1, is a canceled account's data legally required to be *gone* (GDPR erasure → hard delete, bounded and transacted) or merely inaccessible (→ `deletedAt` + retention job, which makes the mistake recoverable instead of just harder)? That's a compliance question I shouldn't guess at. Tell me which, and I'll apply findings 1–4 with marker comments and stop there for review.

Two things I owe you plainly: I couldn't run `detect_hazards.py` (Bash approval unavailable), so this is the manual pass — the script would independently have caught 1, 3, 5 and 7. And the file header declares it a deliberately hazard-rich eval fixture, so if a real `payments.ts` exists, this audit isn't it.