Quick flag before the findings: this file's own header says it's a **benchmark eval fixture** — "Deliberately hazard-rich... every hazard here is one that ships in real codebases and passes review" (`benchmarks/fixtures/payments.ts:1-4`). It's not your actual billing module; it's test data for grading how well the poka-yoke skill detects hazards. If you meant a different file, point me at it. Otherwise, here's the audit — the hazards are real either way, and worth knowing if this pattern shows up anywhere in production code.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` (105 lines)

**Verdict**: the webhook handler will execute unauthorized charges from a forged request, and the charge path will double-bill on any retry — fix those two before anything else here.

### 1. Webhook has no signature verification — Security bypass / Silent
**Where**: `payments.ts:93-100`
**Mistake**: `handleWebhook` does `JSON.parse(body)` and acts on `event.type`/`event.data` with no call to Stripe's signature verification (`stripe.webhooks.constructEvent`).
**Consequence**: anyone who can reach this endpoint can POST a fake `invoice.paid` event naming any customer and amount, and `chargeCustomer` will attempt to charge them. Completely silent — looks like a normal webhook.
**Today**: None.
**Device**: verify the signature before parsing, using the raw body and webhook secret; reject with 400 on failure. **Control** — an unverified event can never reach business logic. This is also C7 (unvalidated external input into `any`) — parse into a typed, verified event, not a bare `JSON.parse`.

### 2. `chargeCustomer` has no idempotency key — Money movement / Silent
**Where**: `payments.ts:37-61`
**Mistake**: retries (the function's own `retry` param, or a redelivered webhook/queue message) call `stripe.charges.create` again with no idempotency key attached.
**Consequence**: duplicate charges. This is the textbook version of the incident already in your own memory log this session — 340 customers double-charged via queue redelivery/Stripe timeout, fixed with idempotency keys. Same shape, unfixed, in this file.
**Today**: None — worse, the `catch` swallows the error and `return null` on final failure, so a caller like `handleWebhook` (which never checks the return value) has no idea whether the charge succeeded, failed, or double-fired.
**Device**: require an idempotency key parameter, pass it to Stripe's `idempotencyKey` option, and stop swallowing the error — let it propagate or return a typed result the caller must check. **Control** for the key; the swallowed error is a separate X1 fix (handle it or propagate it, don't `catch` → `return null`).

### 3. `transfer` isn't a transaction and isn't atomic — Money loss / Silent
**Where**: `payments.ts:17-35`
**Mistake**: balance is read, checked, then two separate `update` calls happen with no transaction. Two concurrent `transfer` calls against the same `fromAccount` both read the same starting balance, both pass the check, both subtract — a classic check-then-act race (M5). A crash between the two `update` calls debits the source and never credits the destination — money vanishes with no record.
**Consequence**: silent balance corruption under ordinary concurrent load, not just adversarial conditions.
**Today**: None.
**Device**: wrap both updates in `db.$transaction([...])`, and make the debit conditional — `UPDATE accounts SET balance = balance - amount WHERE id = ? AND balance >= amount`, checking the affected-row count — so insufficient funds is enforced by the write itself, not a separate read. **Control.**

### 4. `purgeCanceledAccounts()` deletes everything canceled if called with no argument — Irreversible data loss / Requires only forgetting
**Where**: `payments.ts:80-91`
**Mistake**: `olderThan` is optional and defaults to `new Date()` — *now*. Omit the argument (easy, since it's optional) and every canceled account, however recently canceled, is permanently deleted.
**Consequence**: irreversible, proportional to your whole canceled-account population, and reachable by forgetting one argument rather than by deliberate misuse.
**Today**: None.
**Device**: make the cutoff required, not defaulted (F3). Separately: it uses `db.$executeRawUnsafe` with a string-interpolated date to run the actual `DELETE`, while a *different* Prisma `findMany` query computes `doomed.length` to report back — the two queries can drift, and the raw-SQL habit is exactly the shape that becomes a SQL injection the day someone reuses it with a less-controlled value. Use a single parameterized delete (Prisma's typed `deleteMany`) and return its actual count. **Control** for the required argument; **Control** for parameterization.

### 5. `updateSubscription` silently no-ops on unknown status — Silent data corruption
**Where**: `payments.ts:67-78`
**Mistake**: the DB row is updated to *any* string passed as `status` (C4, stringly-typed), but the `switch` only handles `"active"` and `"canceled"` with no `default` (F1). Pass `"past_due"`, `"trialing"`, or a typo, and the subscription record changes state while feature entitlements silently freeze in whatever they were.
**Consequence**: customer's DB status and actual feature access diverge, and nothing signals it.
**Today**: None.
**Device**: a literal union for status, validated at the boundary, plus an exhaustive switch with an `assertNever` default arm so a new status variant fails to compile instead of falling through. **Control.**

### 6. `applyDiscount` — unbounded percentage, swappable numeric args
**Where**: `payments.ts:63-65`
**Mistake**: `price` and `percentOff` are adjacent same-type numbers (C1) — easy to transpose at a call site. Neither is bounds-checked; `percentOff > 100` produces a negative price, `percentOff < 0` produces a markup silently disguised as a discount.
**Consequence**: wrong price charged, quietly.
**Today**: None.
**Device**: validate `percentOff` is in `[0, 100]` at the boundary (Control), and consider named/object args to remove the transposition risk (Warning, cheap). Lower priority than 1-5 since it's a pricing display bug, not money already moved.

## Set aside
- `chargeCustomer`'s `sendReceipt`/`retry` boolean flags (C2) — real, but low blast radius next to the idempotency issue in the same function.
- `currency = "usd"` default (F3) — only matters if this system is multi-currency; flag if it is.
- Non-null assertions (`from!.balance`) in `transfer` — masks a real "account not found" case with an obscure crash instead of a handled error; folded into finding 3 since the transaction fix should address both.

Want me to write this to `docs/poka-yoke/audit-2026-08-22.md`, or is this fixture already the "answer key" the benchmark grades against (in which case I'd want to check `benchmarks/results/` before touching anything)?