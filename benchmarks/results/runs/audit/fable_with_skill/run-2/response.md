Using the `audit` mode. Scope: the single file, 105 lines. One note up front: the detector script (`detect_hazards.py`) was blocked by permissions twice, so this is the lens pass only. Also, the file's own header says it's a deliberately hazard-rich eval fixture — so "nervous" is the right instinct.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-21

**Verdict**: `handleWebhook` lets anyone on the internet charge any customer any amount; fix that before anything else.

## Findings

### 1. Unauthenticated webhook drives a charge — money movement / trivial
**Where**: `payments.ts:93-99`
**Mistake**: POST `{"type":"invoice.paid","data":{"customer":"cus_x","amount":999999}}` to the endpoint. No signature check, `JSON.parse` → `any`.
**Consequence**: real Stripe charge, silent. Stripe also redelivers webhooks, so legitimate events double-charge.
**Today**: None
**Device**: `stripe.webhooks.constructEvent(body, sig, secret)` then a zod schema for the payload; pass `event.id` as the idempotency key downstream → **Control**.

### 2. `transfer` is non-atomic and unsigned — money movement / forgetting
**Where**: `payments.ts:17-35`
**Mistake**: two concurrent transfers from one account both pass the balance check (check-then-act across `await`); or call `transfer(to, from, amt)` — same-type adjacent strings compile fine; or pass a negative `amount`, which *passes* the `balance < amount` check and moves money backwards.
**Consequence**: overdraft / wrong-direction transfer; second update failing leaves money destroyed. All silent.
**Today**: None (`from!` hides the null).
**Device**: `db.$transaction` with a conditional debit `UPDATE … SET balance = balance - $1 WHERE id = $2 AND balance >= $1` and check the row count; branded `AccountId` + `Money` type (integer minor units, currency attached, constructor rejects ≤ 0); required `IdempotencyKey` → **Control**.

### 3. `chargeCustomer` retries without an idempotency key and swallows failure — money / forgetting
**Where**: `payments.ts:37-61`
**Mistake**: a timeout after Stripe succeeded triggers the recursive retry → double charge. Any error returns `null`, so callers proceed as if nothing happened.
**Today**: None
**Device**: required `idempotencyKey` passed in `{ idempotencyKey }` request options; let errors propagate (or return a `Result` union); replace `currency = "usd"` default and the two booleans with a required options object → **Control**. `void sendReceiptEmail` → await it or lint `no-floating-promises` (**Warning**).

### 4. `purgeCanceledAccounts()` with no argument deletes every canceled account — irreversible / forgetting
**Where**: `payments.ts:80-91`
**Mistake**: call it bare. `olderThan || new Date()` = "now" = everything. Raw interpolated SQL; `findMany` count is not the `DELETE` count.
**Today**: None
**Device**: make `olderThan` required, reject cutoffs newer than e.g. 30 days, use `deleteMany` in the same transaction and return *its* count, cap and refuse above N rows; soft-delete if the domain allows → **Control**.

### 5. `updateSubscription` accepts any string and any transition — silent corruption / typo
**Where**: `payments.ts:67-78`
**Mistake**: `"cancelled"` (two l's) writes an unknown status and falls out of the switch doing nothing; `canceled → active` is allowed.
**Device**: literal union `SubscriptionStatus`, single transition function with an allowed-transitions table, `assertNever` default, write + side effect in one transaction → **Control**.

### 6. `applyDiscount(price, percentOff)` — wrong output / swappable
**Mistake**: swap the args, or pass 150 → negative price; float money.
**Device**: `Percent` branded type (0–100) and `Money` → **Control**.

## Set aside
`Account` uses `number`/`string` for balance, currency, status (covered by the types above); `WEBHOOK_TIMEOUT` read at runtime and unused (F4 — validate config at boot).

I have not edited anything. If you want this applied, say which findings and I'll make the changes with `poka-yoke:` marker comments — though since this is a benchmark fixture, you probably want to keep the hazards in place and use this as the grading rubric instead.