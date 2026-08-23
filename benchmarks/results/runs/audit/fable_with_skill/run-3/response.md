The write was denied too, so here's the audit in-conversation.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-21

**Scope**: one file, 105 lines, six exported functions. Manual pass with the contact / fixed-value / motion-step lenses (the detector run wasn't permitted this session).
**Verdict**: `chargeCustomer` can charge a card twice and then report that it charged zero times. Fix that first, then the `transfer` swap-and-race, then the unbounded `DELETE`. Your nervousness is warranted — this passed review because every hazard *looks* like ordinary code.

## Findings (ranked by blast radius × ease)

### 1. Retry double-charges, then returns `null` — `payments.ts:44-60`
**Mistake**: Stripe times out *after* creating the charge; `retry=true` (or a caller retrying on `null`) calls again.
**Consequence**: two real charges, then `null` tells the caller *nothing* happened — inviting a third. No idempotency key anywhere. Fully silent.
**Today**: None → **Device**: required `IdempotencyKey` passed as Stripe's `{ idempotencyKey }` option; throw or return a discriminated result, never `null`. → **Control**

### 2. `transfer(from, to, amount)` swaps silently — `:17`
Both are `string`; `transfer(to, from, n)` compiles and moves money the wrong way. **Today**: None → branded `SourceAccountId`/`DestinationAccountId` → **Control** (object param `{from, to}` is the cheap Warning fallback).

### 3. `transfer` is a check-then-act race across two unrelated writes — `:21-32`
Two concurrent debits both pass the balance check and both write from the stale value; a crash between updates debits one side only. **Today**: None → one `$transaction` with `UPDATE … SET balance = balance - $n WHERE id = $from AND balance >= $n`, assert 1 row, plus `CHECK (balance >= 0)` in the schema. → **Control**

### 4. `to!` on a missing account: money leaves, never arrives — `:21,27,31`
If `to` doesn't exist, the debit succeeds and the credit throws. Partial, silent. → resolve both accounts before any write, ban `!` via `no-non-null-assertion`; fully closed by the transaction in #3. → **Control**

### 5. `purgeCanceledAccounts()` with no arg deletes every canceled account — `:80-91`
`olderThan` defaults to `new Date()` = "now", so the raw `DELETE` matches everything canceled, ever, uncapped, irreversible. Also `$executeRawUnsafe` with string interpolation. → make the cutoff required with a minimum age floor, cap rows / require `{confirmRows}`, use parameterized `deleteMany` and assert the returned count matches `doomed.length`. → **Control**

### 6. `handleWebhook` charges from an unverified, unparsed body — `:93-100`
No signature check, `JSON.parse` → `any`, so anyone who can POST can drive `chargeCustomer(anyCustomer, anyAmount)`. `event.data.amount` is probably `undefined` (Stripe's field is `amount_paid`), currency silently defaults to `usd`, and charging on `invoice.paid` is charging an invoice that's *already paid*. → `stripe.webhooks.constructEvent`, a zod schema, `event.id` as idempotency key. → **Control**

### 7. `updateSubscription` writes any string, then switches without `default` — `:67-78`
`"cancelled"` writes a nonsense status to the DB *before* the switch silently falls through; `canceled → active` is allowed. → literal-union status, a single `transition()` function doing write + side effect in one transaction, `assertNever` default. → **Control**

### 8. Three positional flags `currency, sendReceipt, retry` — `:40-42`
`chargeCustomer(id, 500, "eur", false)` reads as "no retry" but kills the receipt; `currency="usd"` default charges EUR accounts in USD. → `Money` carrying currency + options object with literal unions. → **Control**

### 9. Money as bare `number`, mixed units — `:12,17,63`
`transfer` takes `amount`, `chargeCustomer` takes `amountCents` — same module, two units. `applyDiscount` yields fractional cents. → integer `Money {cents, currency}` with explicit rounding. → **Control**

### 10. `void sendReceiptEmail(...)` — `:52`
Email failure vanishes. → outbox row in the same transaction (Control) or at minimum `await` + `no-floating-promises`. → **Warning** as written, since no outbox table exists yet.

## Set aside
Unused `WEBHOOK_TIMEOUT` string env read (F4); `Account.currency/status: string` (C4, covered by #8/#7); `JSON.parse` → `any` (folded into #6).

---

**Recap**: Ten findings, all rung None today; nine reach Control with branded IDs, a `Money` type, a required idempotency key, a single transaction in `transfer`, and a guarded purge. Per the audit skill I've proposed only — no edits. Two things I couldn't do: run `detect_hazards.py` and write `docs/poka-yoke/audit-2026-08-21.md` (both denied); say the word and I'll apply the devices with `poka-yoke:` marker comments, starting with #1–#3.

One note: the file header says this is a deliberately hazard-rich eval fixture — if "ship it" meant the benchmark rather than real billing code, then it's doing its job and should stay as-is.