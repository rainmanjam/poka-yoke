File write wasn't granted either, so here's the audit inline. (One honest note up front: the file header says it's a deliberately hazard-rich eval fixture — the findings hold either way.)

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-21

**Scope**: one file, 6 exported functions. Detector run was denied; this is the three-lens read.
**Verdict**: two things can lose money before anyone notices — `purgeCanceledAccounts()` with no argument, and `transfer()`. Fix those first.

### 1. Purge with no argument deletes *every* canceled account — irreversible / just forgetting
`payments.ts:81` — `olderThan || new Date()` makes the cutoff *now*. Raw interpolated SQL, no transaction, no cap. Return value is the pre-delete `findMany` count, so the log looks fine.
**Device**: required `{ olderThan, maxRows }`, reject cutoffs inside a retention window, `deleteMany` (parameterized), return the DB's affected count → **Control**.

### 2. `transfer(to, from, amount)` compiles — money moves the wrong way / silent
`payments.ts:17` — two adjacent `string`s.
**Device**: branded `AccountId` + `transfer({ from, to, amount })` → **Control**.

### 3. `transfer` races and half-writes — money vanishes / needs only concurrency
`payments.ts:18-32` — check-then-act on balance (two concurrent calls both pass), two updates with no transaction (debit lands, credit fails), `from!`/`to!` discover a missing `to` *after* debiting, and no currency check (USD→EUR at 1:1).
**Device**: one `$transaction`; balance check inside the `UPDATE ... WHERE balance >= amount` so it's atomic; `CHECK (balance >= 0)` in the schema → **Control**.

### 4. `chargeCustomer` retry double-charges — money / needs only a timeout
`payments.ts:55-58` — if Stripe times out *after* creating the charge, the retry charges again. No idempotency key. Then the catch returns `null`, so callers can't distinguish charged / not charged / charged twice.
**Device**: required `IdempotencyKey` passed to Stripe, drop the `retry` flag, throw instead of `null` → **Control**.

### 5. Webhook charges on unverified `any` — money / anyone with the URL
`payments.ts:93-100` — no signature check, `JSON.parse` → `any`, `amount` charged as cents whatever unit arrived, currency defaults to `"usd"`. And charging on `invoice.paid` is itself a double-bill. `WEBHOOK_TIMEOUT` is read and unused.
**Device**: `stripe.webhooks.constructEvent` (verifies and types), zod on the payload, then decide what `invoice.paid` should actually do → **Control**.

### 6. `updateSubscription` stores any string, then branches non-exhaustively — silent corruption / typo
`payments.ts:67-78` — write happens *before* the switch, so `"cancelled"` is persisted and matches nothing; features stay wherever they were. No transition guard (`canceled → active` is allowed).
**Device**: literal-union status, `assertNever` default, single transition function → **Control**.

### 7. `applyDiscount(percentOff, price)` — wrong price / silent swap
`payments.ts:63` — also accepts 150% or −20%, in floating point.
**Device**: `Money` (integer minor units + currency) and a parsed `Percent` 0–100 → **Control**.

### 8. `void sendReceiptEmail` — failures vanish
`payments.ts:52` — **Device**: await or outbox; `no-floating-promises` as error → **Warning** (Control needs an outbox table this file lacks).

**Set aside**: `balance: number` / `currency: string` on `Account` (root of 2/3/7, fixed by `Money`); boolean flags and `currency="usd"` default (fixed by #4's options object); `process.env` in the handler (unused today).

Per the skill, I've proposed and not edited. Say which findings to apply and I'll make the changes with `poka-yoke:` marker comments. If you want the report on disk, grant the write to `docs/poka-yoke/audit-2026-08-21.md` and I'll re-run it.