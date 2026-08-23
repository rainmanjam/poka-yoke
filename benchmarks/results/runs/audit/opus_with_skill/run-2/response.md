File writes aren't permitted this session either, so the audit stays here. Nothing was changed.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-22

**Verdict**: `purgeCanceledAccounts()` with no argument deletes *every* canceled account, not the old ones. Fix that first.

### 1. Optional cutoff defaults to "delete everything" — irreversible loss / only forgetting
`payments.ts:80` — Call it with no argument from a cron entry expecting a safe default. `cutoff = new Date()` is *now*, so `canceled_at < now` matches every canceled account ever. Returns `doomed.length`, which reads like a plausible success report. **Today: None.**
**Device** → **Control**: make `olderThan` required, add a `max` cap that throws, and delete by the IDs you counted:
```ts
// poka-yoke: an omitted cutoff used to mean "delete every canceled account" [control]
export async function purgeCanceledAccounts(olderThan: Date, opts: { max: number }) {
  const doomed = await db.accounts.findMany({ where: {...}, select: { id: true } });
  if (doomed.length > opts.max) throw new Error(`refusing to purge ${doomed.length}`);
  return db.accounts.deleteMany({ where: { id: { in: doomed.map(a => a.id) } } });
}
```
Closes two sub-hazards with it: the `$executeRawUnsafe` interpolation (line 86, injection surface *and* a second predicate that can drift from the first), and the race between counting and deleting.

### 2. Webhook charges from unsigned input — money + auth bypass / silent
`payments.ts:93` — No signature check, `JSON.parse` into `any`, then `chargeCustomer` with attacker-chosen customer and amount. Even honest traffic double-charges: Stripe redelivers by design, and `invoice.paid` means the money *already* moved. **Today: None.**
**Device** → **Control**: `stripe.webhooks.constructEvent(rawBody, sig, secret)`, then zod, then dispatch. Needs the **raw** body — verification over a re-serialized body fails intermittently, which is how teams end up switching it off. (`WEBHOOK_TIMEOUT` on line 95 is read and never used.)

### 3. `transfer` accepts a negative amount — money creation / reachable input
`payments.ts:21` — The guard is `from.balance < amount`; any balance exceeds a negative number, so it passes and the two updates run *backwards*, unbounded. Silent, and the return value looks like success. **Device** → **Control**: a `Money` type whose constructor can't hold a negative.

### 4. `transfer` isn't atomic and asserts away its own null checks — silent money destruction
`payments.ts:25-32` — Debit commits, then `to!.balance` throws on a nonexistent destination. Money leaves and never lands. The `!` is what lets it compile. Also a check-then-act race: two concurrent transfers both pass line 21 and overdraw.
**Device** → **Control**: one `$transaction`, real null branches, and the balance moved into the `where` clause so the guard is unskippable:
```ts
const debited = await tx.accounts.updateMany({
  where: { id: fromAccount, balance: { gte: amount } },
  data: { balance: { decrement: amount } },
});
if (debited.count !== 1) throw new Error("insufficient funds");
```
Plus `CHECK (balance >= 0)` so the invariant survives anything that isn't this code path.

### 5. Retry with no idempotency key — duplicate charges / silent
`payments.ts:55-60` — A timeout is precisely the case where the charge *did* succeed and the response was lost; the recursion charges again. Then `catch` returns `null`, which every caller here ignores, so success and failure are indistinguishable. **Device** → **Control**: a **required** key parameter backed by `UNIQUE (customer_id, idempotency_key)`. An optional key is rung zero in a costume.

### 6. Swappable IDs and adjacent booleans — wrong-account movement / silent and plausible
`payments.ts:17`, `:37` — `transfer(dst, src, amt)` compiles. `chargeCustomer(id, amt, "usd", false, true)` — `sendReceipt` and `retry` are both `bool` and read identically either way. **Device** → **Control**: branded `SourceAccountId`/`DestinationAccountId`, options object for the flags.

### 7. Stringly-typed status, non-exhaustive switch — entitlement drift / only forgetting
`payments.ts:70` — `"cancelled"` (British spelling) writes the DB, matches no case, falls through with no default. Canceled customer keeps paid features. Nothing throws. **Device** → **Control**: literal union + `assertNever(status)` default arm, so adding a status breaks the build here. Also: the write and the feature toggle aren't in one transaction, and nothing validates the *transition* (`canceled → active` is reachable).

### 8–9. Money as float
`applyDiscount(20, 100)` swaps silently; `percentOff = 150` returns a negative price. `Account.balance: number` + no currency comparison in `transfer` means a USD→EUR transfer moves nominal units and corrupts both balances. **Device** → **Control**: `Money { amountMinor: bigint; currency }`, mixed-currency arithmetic that won't typecheck.

**Set aside (3)**: `void sendReceiptEmail` (line 52) opts out of `no-floating-promises`; `currency = "usd"` default given `Account` carries its own; and none of the type-level devices are load-bearing without `strict: true` + `tsc --noEmit` as a required gate — worth confirming before the branding work.

---

`★ Insight ─────────────────────────────────────`
Findings 3 and 7 are the same shape as each other: a validation that *passes* when it should fail. The negative-amount guard and the empty switch both go quiet rather than loud, which is why review missed them — there's nothing to see. Loud failures are cheap; quiet ones compound.

Note what finding 4's `updateMany` does — moving the balance check from an `if` into the `where` clause converts a rung-2 assertion into a rung-1 constraint, because the database now refuses the write rather than your code choosing to.
`─────────────────────────────────────────────────`

Two notes: the file header calls this an eval fixture, "deliberately hazard-rich" — if it's genuinely shipping, that header is itself worth fixing. And I couldn't run `detect_hazards.py` (permission), so this is lens-work only; the detector may add mechanical hits I didn't reach.

**Your call on one thing before I touch anything**: finding 1's `max` cap needs a number, and that's a domain decision I shouldn't make. Too low and the cron fails nightly until someone raises it — which trains people to raise it. Too high and it isn't a device. What's the largest legitimate nightly purge you'd expect? Related: should exceeding it throw, or purge the oldest `max` and report the remainder?