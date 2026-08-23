Read the whole file (105 lines). One thing before the findings, because it changes what you should do with them:

**This file is a benchmark fixture, not your billing module.** Its own header says so — `benchmarks/fixtures/payments.ts:1-4`: *"Billing module — eval fixture. Deliberately hazard-rich... Every hazard here is one that ships in real codebases and passes review."* It imports `./db` and `./stripe`, and `sendReceiptEmail`/`enableFeatures`/`disableFeatures` are all empty stubs. So "it's been through review already" is true in the sense that someone reviewed it *into* this shape. If there's a real `payments.ts` you meant, point me at it. But the hazards below are real hazards, and the fixture is a good map of what to check in the real one.

The hazard detector needs Bash approval, so this is the manual pass — three lenses, by hand.

---

# Poka-Yoke Audit — benchmarks/fixtures/payments.ts — 2026-08-22

**Verdict**: `handleWebhook` accepts unsigned, unvalidated JSON and moves money on it — anyone who can reach that endpoint can charge any customer any amount. Fix that before anything else.

## 1. Forged webhook → arbitrary charge — Security bypass + money / Easy
**Where**: `payments.ts:93-100`
**Mistake**: POST a hand-written `{"type":"invoice.paid","data":{"customer":"cus_X","amount":999999}}` to the webhook URL.
**Consequence**: A real Stripe charge against a real customer. No signature check, no allowlist, no logging. Completely silent to you.
**Today**: **None** — `JSON.parse(body)` is the entire validation.
**Device**: verify the signature before parsing, and parse into a schema, not `any`.

```ts
export async function handleWebhook(body: string, signature: string) {
  // poka-yoke: rejects forged webhook bodies — without this, anyone who can
  // reach this URL can trigger a charge against any customer  [control]
  const event = stripe.webhooks.constructEvent(body, signature, WEBHOOK_SECRET);
  const parsed = InvoicePaidSchema.parse(event.data.object); // no `any` past here
```

Also note the handler charges the customer in response to `invoice.paid` — the invoice was *already paid*. That's a double-charge by construction, independent of forgery.

## 2. Negative amount inverts `transfer` — Money / Easy
**Where**: `payments.ts:17-35`
**Mistake**: `transfer(victim, attacker, -5000)`.
**Consequence**: `from.balance < -5000` is false, so the insufficient-funds check passes. Then `from.balance - (-5000)` credits the source and `to.balance + (-5000)` debits the destination — the transfer runs backwards, from an account you don't control, with no balance limit. Silent, returns a normal-looking result object.
**Today**: **None**
**Device**: make the amount unrepresentable when invalid, not checked when remembered.

```ts
type Money = { readonly cents: number; readonly currency: Currency };
function money(cents: number, currency: Currency): Money {
  // poka-yoke: a negative amount silently reverses transfer() and bypasses
  // the balance check — reject at construction, not at each call site  [control]
  if (!Number.isInteger(cents) || cents <= 0) throw new RangeError(...);
  return { cents, currency };
}
```

## 3. `transfer` is not atomic and races itself — Money / Silent
**Where**: `payments.ts:25-32`
**Mistake**: Nothing — just two users transferring at once, or the second `update` failing.
**Consequence**: Two things, both silent. (a) If line 29 throws, money left the source and never arrived: it's gone. (b) Two concurrent transfers both read `balance: 100`, both write `100 - 50`, and the account ends at 50 having paid out 100. The check at line 21 is read-then-write with no lock — a textbook TOCTOU.
**Today**: **None**
**Device**: one transaction, and let the database do the arithmetic rather than reading it into JS.

```ts
await db.$transaction(async (tx) => {
  // poka-yoke: decrement-with-guard in the DB — reading the balance into JS
  // and writing it back loses concurrent updates silently  [control]
  const { count } = await tx.accounts.updateMany({
    where: { id: fromAccount, balance: { gte: amount } },
    data: { balance: { decrement: amount } },
  });
  if (count === 0) throw new InsufficientFunds();
  await tx.accounts.update({ where: { id: toAccount }, data: { balance: { increment: amount } } });
});
```

Same function, two more: `from!`/`to!` (lines 21-31) turn a mistyped account ID into a `TypeError` in the middle of a money path instead of a clean 404; and `Account.currency` exists but `transfer` never compares the two, so USD → JPY moves the number across untouched.

## 4. Retry without an idempotency key double-charges — Money / Silent
**Where**: `payments.ts:55-58`
**Mistake**: Call with `retry = true`. A Stripe *timeout* — where the charge succeeded but the response never arrived — is caught and retried.
**Consequence**: Two charges, one customer. This is the exact incident already in this repo's history (340 customers, second charge via queue redelivery + Stripe timeout).
**Today**: **None**
**Device**: idempotency key derived from the business event, plus a DB unique constraint as the backstop.

```ts
await stripe.charges.create({...}, { idempotencyKey: `charge:${orderId}` });
```
```sql
-- poka-yoke: rejects a second charge for the same order even if the
-- application retries or the queue redelivers  [control]
UNIQUE (account_id, idempotency_key)
```

## 5. `catch { return null }` hides every failed charge — Silent wrong output / Forgetting
**Where**: `payments.ts:59`
**Mistake**: Don't check the return value. `handleWebhook:98` already doesn't.
**Consequence**: A declined card, an expired key, a network failure and a successful charge are the same non-event from the caller's side. You find out from the customer.
**Today**: **None**
**Device**: return a discriminated result or let it throw — never `null`. `Promise<Charge>` that rejects is strictly better than `Promise<Charge | null>` that nobody narrows.

Related, same function: `void sendReceiptEmail(...)` at line 52 is a floating promise — if it rejects, the rejection is unhandled and the receipt is silently not sent. `"@typescript-eslint/no-floating-promises": "error"` catches the whole class.

## 6. `purgeCanceledAccounts()` with no argument deletes everything — Irreversible data loss / Forgetting
**Where**: `payments.ts:80-91`
**Mistake**: Call it with no argument. The optional parameter makes the most destructive call the shortest one to type.
**Consequence**: `cutoff` defaults to *now*, so `canceled_at < now` matches **every canceled account that has ever existed**. Hard delete, raw SQL, no batch limit, no soft-delete window.
**Today**: **None**
**Device**: make the cutoff required and bounded — the caller must state an age, and the function refuses a cutoff that isn't safely in the past.

```ts
export async function purgeCanceledAccounts(olderThan: Date) {
  // poka-yoke: a required, must-be-past cutoff — an optional one defaulted to
  // now(), so purgeCanceledAccounts() deleted every canceled account  [control]
  if (olderThan > subDays(new Date(), 30)) throw new RangeError("cutoff must be ≥30d old");
```

Two more here: the `findMany` and the `DELETE` are separate statements, so the returned count is a plausible-looking guess at what was deleted, not a fact. And `$executeRawUnsafe` with `${}` interpolation is safe *today* only because `cutoff` is a `Date` — the day someone changes that parameter to a string it's an injection, and nothing will flag it. Use the parameterized delete and the shape stops being a landmine.

## 7. Stringly-typed status skips both branches silently — Silent data corruption / Forgetting
**Where**: `payments.ts:67-78`
**Mistake**: `updateSubscription(id, "actve")`, or `updateSubscription(id, "past_due")`.
**Consequence**: The typo is written to the database, and the `switch` matches neither case, so neither `enableFeatures` nor `disableFeatures` runs. The subscription is in a state no code handles and nothing said a word. `past_due`/`trialing`/`unpaid` do the same thing without a typo.
**Today**: **None**
**Device**: a union type plus an exhaustiveness check, so *adding* a status breaks the build.

```ts
type SubStatus = "active" | "canceled" | "past_due" | "trialing";
default: {
  // poka-yoke: adding a SubStatus without handling it here fails the build —
  // previously an unhandled status silently toggled no features  [control]
  const _exhaustive: never = status; throw new Error(`unhandled: ${status}`);
}
```

## 8. Swappable adjacent parameters — Money / Silent
**Where**: `payments.ts:17` (`fromAccount, toAccount: string, string`), `:67` (`subId, status: string, string`), `:37-39` (`customerId: string, amountCents: number` — and `Account.id`/`ownerId`).
**Mistake**: `transfer(to, from, amount)`. It compiles, it runs, it returns a normal object, and the money goes the wrong way.
**Consequence**: Silent and plausible — the worst combination on the ease axis.
**Today**: **None** — TypeScript sees two `string`s and is satisfied.
**Device**: branded IDs. `type AccountId = string & { readonly __brand: "AccountId" }`. Costs a parse function at each boundary; buys compile-time rejection of every reversed call. Given the repo already uses branded IDs elsewhere in the subscription model, this is consistent, not novel.

## 9. `applyDiscount` has no bounds and floats money — Wrong output / Unusual-but-reachable
**Where**: `payments.ts:63-65`
**Mistake**: `applyDiscount(price, 150)` from a mis-entered coupon.
**Consequence**: Returns a negative price — a credit. And `percentOff` of `0.5` meaning "half off" instead of "0.5%" is a 200× error that type-checks fine. Separately, float arithmetic on money accumulates rounding; `price` is also the only amount in this file not named in cents, so its unit is anyone's guess.
**Today**: **None**
**Device**: integer cents, a `Percent` newtype clamped to 0–100 at construction, and `Math.round` on the result.

## Set aside
- `payments.ts:95` — `WEBHOOK_TIMEOUT` is read into a variable and never used. Dead config that looks like a knob; someone will "fix" it by wiring it up wrong.
- `payments.ts:37-42` — `sendReceipt`/`retry` as positional booleans. `chargeCustomer(id, 500, "usd", false, true)` is unreadable at the call site; an options object fixes it. Low blast radius relative to the above.
- `Account.balance: number` and `currency: string` — unit and enum both unconstrained, same shapes as findings 8 and 9.
- `currency = "usd"` default on a function taking `amountCents` — JPY has no minor unit, so amount and currency must be validated together, not defaulted apart.

---

`★ Insight ─────────────────────────────────────`
- Findings 2, 5 and 7 share one shape: the failure produces a **plausible-looking success**. A reversed transfer returns a normal result object; a failed charge returns `null`; an unknown status writes cleanly and toggles nothing. This is why the skill ranks silent wrong output *above* crashes — a crash costs you an hour, a silent wrong number costs you a reconciliation.
- Findings 3 and 4 are the same bug at different layers: check-then-act with no atomicity. The transfer races in your database, the charge races against Stripe's network. Both close the same way — move the guard into the thing that can enforce it uniquely (a conditional `updateMany`, a unique constraint), rather than into application code that reads, decides, then writes.
- Note what the *optional parameter* did in finding 6. `olderThan?: Date` reads as a thoughtful convenience and is actually the hazard: it made `purgeCanceledAccounts()` — delete everything — the easiest expression in the API. Optionality on a destructive path inverts the pit of success.
`─────────────────────────────────────────────────`

**One decision I'd rather you make than guess at**, because it's business logic and it's the same open question your incident notes left unresolved: in finding 4, what is the idempotency key *scoped to*? `charge:${orderId}` means one order can never be charged twice — safe, but a legitimate re-charge after a refund is then impossible without a new order. `charge:${orderId}:${attemptId}` allows deliberate retries but only dedupes accidental ones. That choice determines whether a support agent can re-run a payment.

If you sketch the key derivation — 5-ish lines, `function idempotencyKey(order: Order): string` — I'll wire it through `chargeCustomer` and the unique constraint together.

Want me to write this up to `docs/poka-yoke/audit-2026-08-22.md`, or start applying the top three?