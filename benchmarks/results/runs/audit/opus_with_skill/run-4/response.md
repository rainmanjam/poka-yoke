File write needs approval too, so here it is in the conversation. Scope: that one file, 105 lines, read in full and run through the three lenses.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts`

**Verdict**: `handleWebhook` verifies no signature and responds to `invoice.paid` by charging the customer *again*. Anyone who can POST to that endpoint can move arbitrary money from arbitrary customers. Fix that before anything else here.

---

### 1. Unsigned webhook is an arbitrary-charge primitive — money / needs only forgetting
`payments.ts:93`
**Mistake**: trust a POST body as a Stripe event, no `constructEvent`.
**Consequence**: `{"type":"invoice.paid","data":{"customer":"cus_X","amount":999999}}` charges a real customer. Silent — looks like normal webhook traffic. Compounded by the logic: `invoice.paid` means money already arrived, and the handler charges again. Stripe retries webhooks, so even *legitimate* traffic double-charges.
**Today**: None. **Device** → **Control**:

```ts
// poka-yoke: an unsigned body cannot become a StripeEvent, so no forged POST moves money [control]
export async function handleWebhook(rawBody: Buffer, signature: string) {
  const event = stripe.webhooks.constructEvent(rawBody, signature, WEBHOOK_SECRET); // throws
  const parsed = StripeEventSchema.parse(event);                                    // zod, throws
  switch (parsed.type) {
    case "invoice.paid": return recordPayment(parsed.data);   // NOT chargeCustomer
    default: return assertNever(parsed);
  }
}
```

### 2. Negative `amount` reverses `transfer` and drains any account — money / silent
`payments.ts:17`
**Mistake**: pass a negative amount (unvalidated API field, or a subtraction that went below zero upstream).
**Consequence**: `from.balance < -100` is **false**, so the one guard passes. Then `balance - (-100)` *credits* the sender and `balance + (-100)` *debits* the recipient. `transfer(mine, victim, -100)` is free money out of someone else's account. Silent.
**Today**: None — the check present is bypassed by the sign.
**Device** → **Control**: a `Money` constructor that rejects non-positive values, so a negative amount cannot be constructed. Also kills money-as-float.

### 3. `purgeCanceledAccounts()` with no args deletes every canceled account ever — irreversible loss / silent
`payments.ts:80`
**Mistake**: call it the natural way — no arguments — from cron.
**Consequence**: `olderThan || new Date()` makes the default cutoff **now**, so the no-argument case is the maximally destructive one. Hard DELETE, no cap, no dry run. Separately: the `findMany` and the raw `DELETE` are two independent queries with hand-duplicated predicates (`canceledAt` vs `canceled_at`), so the returned count is what the SELECT saw, not what the DELETE removed — the number you'd page on isn't the number of rows destroyed.
**Device** → **Control**: required cutoff, `maxRows` cap, `dryRun`, and delete by the IDs you counted (which also drops `$executeRawUnsafe`).

### 4. `transfer` isn't atomic, and the destination is dereferenced *after* the debit — money / silent
`payments.ts:17-32` — three failures in six lines:
- `to` is fetched at :19 but first dereferenced at :31, **after** the debit at :25 commits. Bad destination ID → sender debited, `to!.balance` throws, money gone. No transaction, nothing rolls back.
- Read-modify-write with an absolute value: two concurrent transfers both read 100, both write 40 — one debit vanishes.
- `from!` / `to!` switch off the type system exactly where it mattered.

**Device** → **Control**: one `$transaction`, `findUniqueOrThrow` (removes the `!`), atomic `{ decrement }` / `{ increment }`, plus `CHECK (balance >= 0)` in the schema — the DB is the only guard every code path shares.

### 5. `chargeCustomer` retries with no idempotency key, then swallows the error — money / silent
`payments.ts:37`
The `catch` retries on *any* exception, including a timeout where Stripe already created the charge. Two charges, one order. Then `return null` makes a payment failure indistinguishable from a decline, a network death, and a bug.
**Device** → **Control**: a **required** `idempotencyKey` param passed to Stripe. An optional key is rung zero in a costume. Let the error propagate instead of returning `null`.

### 6. `updateSubscription` accepts any string, silently handles two — silent corruption / needs only a typo
`payments.ts:67`
Call it with `"cancelled"` (two Ls — the British spelling half your team will type). The DB write at :68 succeeds unconditionally, the switch matches nothing, no default. Subscription reads canceled, customer keeps every paid feature. No error anywhere.
**Device** → **Control**: literal union + `assertNever` default. Also: `canceled → active` is currently reachable from any caller, and the DB write isn't in a transaction with the feature toggle.

### 7-10, briefly
- **`transfer(from: string, to: string)`** `:17` — adjacent same-type params; `transfer(to, from, amt)` compiles and moves money backwards. Branded IDs → Control; an options object → Warning, but free.
- **`applyDiscount(price, percentOff)`** `:63` — swap gives 0 instead of 80; `percentOff` of 150 yields a negative price (a credit); of -50, raises it. Nothing rejects any of it.
- **Currency is a `string` nothing compares** `:13,17,40` — `transfer` never reads `.currency`, so cross-currency movement is a numeric add at an implied 1:1. Plus `currency = "usd"` is a default on something with no safe default.
- **`void sendReceiptEmail(...)`** `:52` — the explicit `void` suppresses the lint that would catch this; errors vanish, and serverless can exit before the send. **Warning** only — TypeScript can't make a dropped promise a type error.

**Set aside**: `WEBHOOK_TIMEOUT` read into a variable and never used (`:95`); `Account.status`/`currency` as `string` (`:14`); `$executeRawUnsafe` not injectable *today* only because a `Date` is interpolated.

**Prerequisite**: every type-level device above is inert without `strict: true` and `tsc --noEmit` as a *required* CI check. Worth confirming first.

`★ Insight ─────────────────────────────────────`
Findings 2 and 3 share a shape worth naming: **the guard exists, and the hazard walks around it.** The balance check in `transfer` is real code that a reviewer's eye lands on and approves — it just doesn't hold for negative inputs. `olderThan || new Date()` looks like a thoughtful default. Both read as *more* careful than the naive version, which is exactly why review passed them. This is why the skill ranks "silent and plausible-looking" as the highest ease-of-mistake: the dangerous code is the code that looks defended.
`─────────────────────────────────────────────────`

---

I've proposed but not edited — per the audit skill, these change interface shapes and ripple through call sites, so they're yours to green-light. Two things I'd want your call on:

1. **Which findings to apply**, and whether I should write the report to `docs/poka-yoke/audit-2026-08-22.md` (the Write was denied — needs your approval).
2. **The idempotency key scope for `chargeCustomer`** — this is a genuine design decision and your domain knowledge beats my guess. Should the key be derived from the order ID (natural, dedupes across all retry paths, but two legitimate charges for one order become impossible), or passed in by the caller (flexible, but each call site must get it right)? Your session notes from earlier today show this exact question came up in the double-charge incident and was left open. If you want to sketch it, the signature is at `payments.ts:37` — the trade-off is dedup strength versus caller flexibility.

Also worth noting: `Bash`, `ctx_execute`, and `Write` all need permission grants in this session, so I couldn't run `detect_hazards.py` to cross-check. It would likely have flagged C1, C2, C6, F2, F3, M2 and X1 mechanically — but the webhook signature gap and the negative-amount bypass are lens findings, not text patterns, so the manual pass was the load-bearing part regardless.