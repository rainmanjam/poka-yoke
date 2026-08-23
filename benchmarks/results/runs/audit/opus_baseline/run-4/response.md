Before the findings — one thing you should know up front. The file's own header (line 1-4) says:

```
// Billing module — eval fixture.
// Deliberately hazard-rich, in ways that look like ordinary working code rather than like a quiz.
```

This is `benchmarks/fixtures/` — it's the graded input for `benchmarks/run.py`, not shipping code. So "been through review already" isn't quite the situation: nothing here was meant to survive review. If you have a *real* payments module you meant to point me at, tell me the path and I'll redo this against it. Reviewing the fixture is still worth doing, so here it is in full.

**Scope**: `benchmarks/fixtures/payments.ts`, 105 lines, read in full. Detector script needed approval so this is by hand.

**Verdict**: `handleWebhook` charges real money based on an unauthenticated, unverified HTTP body — everything else on this list is second.

---

### 1. Unauthenticated webhook moves money — security bypass / trivial
**Where**: `payments.ts:93-100`
**Mistake**: POST arbitrary JSON to the webhook endpoint.
**Consequence**: `JSON.parse(body)` → `chargeCustomer(event.data.customer, event.data.amount)`. Any attacker charges any customer any amount. No signature check, no replay guard. Silent — it looks exactly like legitimate traffic in your logs.
**Today**: None.
**Device**: `stripe.webhooks.constructEvent(rawBody, sig, secret)` — takes the raw body and throws on bad signature, so an unverified event can't reach the handler. → **Control**

Two more in the same function: Stripe *already collected* on `invoice.paid`, so charging again is a duplicate by construction; and Stripe retries webhooks, so redelivery charges twice. That's the failure mode from your 340-customer incident.

### 2. `transfer` is not atomic — irreversible money loss / silent
**Where**: `payments.ts:17-35`
**Mistake**: Call it. Nothing unusual required.
**Consequence**: Read-check-write across three round trips with no transaction. Two concurrent transfers both read balance 100, both pass the check, both write — one debit vanishes. Worse: if `to` doesn't exist, `from!` passes, the debit commits (line 25), then line 31 throws on `to!.balance`. Money debited, never credited, no rollback.
**Today**: None.
**Device**: Wrap in `db.$transaction` and make the debit conditional in SQL, not in JS:
```ts
// poka-yoke: conditional update makes overdraft unrepresentable — a check in JS
// can be raced between the read and the write [control]
UPDATE accounts SET balance = balance - $amt WHERE id = $from AND balance >= $amt
```
Zero rows affected → throw. → **Control**

### 3. `transfer` mints money three different ways — irreversible / trivial
Same function, and each is independently exploitable:

- **Negative amount**: `amount = -100` → `from.balance < -100` is false, check passes → source *gains* 100, destination is drained with **no balance check on it at all**.
- **Self-transfer**: `from === to` reads the same row twice at balance `B`. Debit writes `B - amt`, credit then writes the stale `B + amt`. Net: account gains `amt`.
- **Currency ignored**: `Account.currency` exists and is never read. 100 USD out, 100 EUR in.

**Device**: A branded `PositiveAmount` parsed at the boundary, `if (from === to) throw`, and a currency equality assert — plus #2's transaction, which kills the self-transfer read anyway. → **Control**

### 4. Retry with no idempotency key — double charge / silent
**Where**: `payments.ts:56-58`
**Mistake**: Pass `retry = true`.
**Consequence**: Retries on *any* exception, including a timeout where the charge actually succeeded. Customer charged twice. Exactly your incident.
**Device**: `stripe.charges.create({...}, { idempotencyKey })` where the key is caller-supplied and derived from the order — plus a unique DB constraint so a second insert can't land. → **Control**

### 5. Swallowed exception returns `null` — silent wrong output / trivial
**Where**: `payments.ts:59`
**Mistake**: Not check the return.
**Consequence**: `catch { return null }`. Failure and success have the same shape at the call site; `if (charge)` is easy to forget, and TypeScript won't make you. You lose the Stripe error entirely — no decline code, nothing.
**Device**: Return `Result<Charge, ChargeError>` (or just rethrow). A union forces the caller to discriminate. → **Control**

### 6. `purgeCanceledAccounts()` with no argument deletes everything — irreversible / one omission
**Where**: `payments.ts:80-91`
**Mistake**: Forget the parameter.
**Consequence**: `olderThan || new Date()` makes the cutoff *now* — deletes every canceled account that ever existed. The optional param means the destructive default is the one you get by typing less. The `doomed` count is also a lie: it's a separate query from the DELETE, so the returned number and the rows removed can differ.
**Device**: Make `cutoff` required and non-defaultable, add `LIMIT`, and delete by the IDs you actually selected so the count is the truth. → **Control**

Also: `$executeRawUnsafe` with string interpolation. `toISOString()` happens to be safe today, but this is one refactor from injection — use the parameterized client.

### 7. Swappable parameters — silent wrong result / easy
**Where**: `transfer(from: string, to: string, ...)` line 17; `applyDiscount(price: number, percentOff: number)` line 63; `chargeCustomer(..., sendReceipt: boolean, retry: boolean)` line 41-42.
**Mistake**: `transfer(dst, src, amt)` — money goes the wrong way and every type checks. `applyDiscount(20, 100)` instead of `(100, 20)`. `chargeCustomer(id, 500, "usd", false, true)` — which boolean is which?
**Device**: Branded `AccountId`, and options objects for the booleans: `{ sendReceipt: false, retry: true }`. Names at the call site can't be transposed. → **Control**

`applyDiscount` also doesn't bound `percentOff` — 150 returns a negative price, i.e. a refund.

### 8. Stringly-typed status, non-exhaustive switch — silent / one typo
**Where**: `payments.ts:67-78`
**Mistake**: `updateSubscription(id, "cancelled")` — British spelling.
**Consequence**: The DB write on line 68 succeeds, the switch matches nothing, no default, `disableFeatures` never runs. Customer keeps paid access indefinitely and nothing reports it. Also the write and the side effect aren't atomic — crash between them and the state diverges.
**Device**: `type SubStatus = "active" | "canceled" | "past_due"` plus `default: assertNever(status)`, so adding a variant is a compile error rather than a runtime no-op. → **Control**

---

**Set aside (5)**: `void sendReceiptEmail(...)` floating promise on line 52 (errors vanish — fix with `no-floating-promises`); `balance: number` is a float, money should be integer minor units; `amountCents` assumes two decimals, wrong for JPY; unused `timeout` on line 95; `Account.status`/`currency` untyped strings (folded into #8).

`★ Insight ─────────────────────────────────────`
- The pattern connecting #2, #4 and #6: each has a **check in application code that the database could enforce instead**. A JS `if` can be raced, forgotten, or refactored away; a `WHERE balance >= amt` or a `UNIQUE` constraint cannot. Push invariants down to the layer that can't be bypassed.
- #5 is worth dwelling on — it ranks above a crash on this repo's own scale. A thrown exception is loud and stops the line. `return null` produces a plausible-looking value that flows onward and corrupts things far from the origin.
- #8 is the `assertNever` trick: giving the `default` branch a `never` parameter turns "someone added a status" from a silent runtime miss into a build failure. The device is the type system refusing to compile, not a reviewer noticing.
`─────────────────────────────────────────────────`

I've not touched the file — these ripple through call sites and you should see the plan first.

**One thing I'd like your call on**, because it's a policy question rather than a technical one: for #4, what should the idempotency key be scoped to? Your `.remember/` notes show this exact decision was left open after the incident. The options trade off differently:

- **Order ID** — natural, but a legitimate retry of a genuinely new charge for the same order gets rejected.
- **`(customer, amount, time-bucket)`** — catches accidental doubles, but silently merges two intentional identical charges.
- **Caller-supplied, required** — pushes the decision to whoever knows the business context, at the cost that every call site must now think about it.

If you tell me which, I'll write the `chargeCustomer` signature around it — that's the one where your domain knowledge beats my guess. Want the full report written to `docs/poka-yoke/audit-2026-08-22.md`, or is in-conversation fine?