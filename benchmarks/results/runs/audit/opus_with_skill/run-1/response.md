File writes aren't approved in this session either, so here it is inline.

**Scope**: `benchmarks/fixtures/payments.ts`, all 104 lines, 6 exports. The detector script needs Bash approval I don't have, so I ran the three lenses by hand instead. (Worth knowing: the file's own header says it's a deliberately hazard-rich eval fixture — the hazards are real either way, so I audited it as written.)

**Verdict**: `purgeCanceledAccounts()` with no arguments deletes every canceled account that has ever existed. Fix that first.

---

### 1. `purgeCanceledAccounts()` — irreversible mass delete, zero-argument · `:80`

`olderThan || new Date()` makes the default cutoff *now*, so `canceled_at < now` matches **everything**. Hard delete, no cap, no dry-run, no soft-delete. The optional parameter defaults to the maximally destructive value.

Three riders: the `findMany` and the raw `DELETE` are separate statements outside a transaction, so `doomed.length` undercounts the damage; `$executeRawUnsafe` with an interpolated value is safe *today* only because `toISOString()` is; and `canceledAt` vs `canceled_at` is the same predicate spelled twice, free to drift.

**Today**: nothing. **Device** → **Control**: required `canceledBefore`, a `maxRows` cap that throws when exceeded, `apply: boolean` defaulting to dry-run, and one parameterized `deleteMany`.

### 2. `transfer` — five mistakes in eighteen lines · `:17`

- **Negative amount inverts it.** `transfer(a, b, -100)`: `balance < -100` is false, guard passes, then `balance - (-100)` *credits* the source. Any endpoint forwarding an amount from a request body is a money printer.
- **Swapped args** — two adjacent `string` params (C1). `transfer(dst, src, amt)` compiles and reverses the payment.
- **Debit commits, then it throws.** `to!` is dereferenced at `:31`, *after* the debit at `:25`. An unknown destination ID debits the source and destroys the money.
- **Check-then-act race** (M5) — balance read at `:18`, written at `:25` as a stale absolute. Concurrent transfers overdraw.
- **Two writes, no transaction** (F5). `currency` exists on `Account` and is never checked, so USD→EUR moves 1:1.

**Device** → **Control**: branded `AccountId`, a `PositiveCents` smart constructor so a negative amount can't be constructed, and a conditional decrement inside `$transaction`:

```ts
const debited = await tx.accounts.updateMany({
  where: { id: args.from, balance: { gte: args.amount } },  // poka-yoke: concurrent transfers cannot overdraw [control]
  data:  { balance: { decrement: args.amount } },
});
if (debited.count !== 1) throw new Error("insufficient funds");
```

Add `CHECK (balance >= 0)` so scripts and `psql` are held to it too.

### 3. `handleWebhook` — unauthenticated input triggers charges · `:93`

No signature verification. `JSON.parse` into `any`. Anyone who can reach the endpoint POSTs `{"type":"invoice.paid","data":{"customer":"cus_x","amount":999999}}` and charges an arbitrary customer an arbitrary amount. No event-ID dedup, so Stripe's redeliveries charge again. And `invoice.paid` — "we were paid" — *takes payment*; a stringly-typed event name over an `any` payload is what hides an inversion that large. `process.env.WEBHOOK_TIMEOUT` is read on the payment path, parsed nowhere, used nowhere (F4).

**Device** → **Control**: `stripe.webhooks.constructEvent(rawBody, sig, secret)` first, zod-parse second, `createMany({skipDuplicates})` against a `UNIQUE(event_id)` table third. Take `rawBody: Buffer` — signature checks fail on re-serialized strings, so the type stops that mistake at the door.

### 4. `chargeCustomer` — double-charges on retry · `:37`

No idempotency key anywhere (M2). The catch can't tell "charge failed" from "charge succeeded, response timed out" — and the timeout case is exactly when `retry` fires. This is the shape of the 340-customer incident already in this repo's history.

Plus: `return null` on any error (X1) means a forgotten null-check reads a failed payment as a completed one, and the Stripe error — declined? network? our bug? — is discarded. Two boolean flag params (C2) make `chargeCustomer(id, 500, "usd", false, true)` unreviewable. `currency = "usd"` is a default with no safe value (F3). `void sendReceiptEmail(...)` loses errors and can be killed by process exit (M6).

**Device** → **Control**: options object, required `idempotencyKey` backed by a unique constraint, `Promise<Charge>` that throws. Retries move to the queue with backoff. Note the key must be reserved in the same transaction as the effect and bound to the payload — a caller that retries into a bare constraint violation has learned nothing about whether the first attempt worked, so replay the stored result.

### 5. `updateSubscription` — a typo silently keeps features on · `:67`

`status: string`. `updateSubscription(id, "cancelled")` writes the garbage value, then matches neither case and falls through — no `default` (F1). A canceled subscriber keeps their features, forever, silently. Any transition is legal too (M3): `canceled → active` re-enables everything with no charge. Write-then-side-effect with no transaction (F5). And two adjacent strings again.

**Device** → **Control**: literal union + `default: assertNever(status)`, both inside `$transaction`, with `@typescript-eslint/switch-exhaustiveness-check` at error level so it holds everywhere.

### 6. `applyDiscount` — unbounded percent, swappable numbers · `:63`

`applyDiscount(20, 100)` — 100% off $20, or $20 off $100? Both compile. `percentOff = 150` returns a **negative price**; `-50` raises it. Float money with no rounding rule, so reconciliation drifts. The module also mixes units: `amountCents` here, `price` there.

**Device** → **Control**: a `Percent` smart constructor rejecting outside [0,100], cents in / cents out, explicit `Math.round`.

### 7. `Account` is where the other six come from · `:9`

`id` and `ownerId` are both bare `string` — `findUnique({where:{id: account.ownerId}})` compiles and returns null. `status` and `currency` are stringly-typed enums every consumer guesses at. `balance: number` is float money with no currency bound to it, so USD and EUR balances add. Brand the IDs, close the enums, make `balance` a `Money` carrying its currency, and the class of bug closes rather than the instances.

---

**Set aside**: the unused `timeout` var, `void sendReceiptEmail`, unused `ownerId`, and the `canceledAt`/`canceled_at` split — all folded into findings above. No style or naming findings; they'd dilute these.

**Prerequisite**: none of the branded types are load-bearing without `strict: true` and `tsc --noEmit` as a *required* CI check. That's the first commit, not the last.

★ Insight ─────────────────────────────────────
Two things worth pulling out of the pattern above. First — five of these seven are *silent*: swapped transfer args, `"cancelled"`, `currency = "usd"`, `return null`, and a 150% discount all produce a confident wrong answer rather than a crash. That's why the audit ranks a crash *below* silent wrong output. Loud failures are cheap.

Second — this file already passed review, which is the point. Review is rung 3 (successive check): a human looking for a mistake they have to remember to look for. Every device above moves the same catch to rung 1, where the mistake has no spelling.
─────────────────────────────────────────────────

I haven't touched any files — audit mode proposes first, since these changes reshape signatures and ripple through call sites.

Two things I'd like from you before applying:

1. **Which findings to apply, and in what order.** My recommendation: 1 and 3 today (both are reachable by someone who isn't even trying), then 4, then the branded types in 7 as the foundation for 2, 5, 6.

2. **One decision that's genuinely yours, not mine** — finding 1's device. I proposed a hard delete with a cap and a dry-run flag, but soft-delete is the higher rung: it makes the mistake *recoverable* rather than merely harder to make. That trade depends on facts I don't have — whether you have a data-retention obligation to actually purge canceled accounts, and whether anything downstream (analytics, billing exports, foreign keys) reads rows it would now still see. If you tell me the retention constraint, I'll pick the shape; if you'd rather write the predicate yourself, `purgeCanceledAccounts` is about 10 lines and it's the one place in this file where the domain rule matters more than the type.