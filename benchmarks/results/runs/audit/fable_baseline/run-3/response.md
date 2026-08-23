The detector needs approval I can't get in this session, so I'm going from a direct read. The file is only 105 lines, which is enough.

One thing before the findings: **this file is not your billing module.** Line 1–4 say it outright — `// Billing module — eval fixture. Deliberately hazard-rich, in ways that look like ordinary working code rather than like a quiz.` It lives in `benchmarks/fixtures/`, and it's the bait the benchmark feeds to models to see whether the audit skill catches things. `./db` and `./stripe` don't exist as real modules. Nothing here should ship anywhere. If a real `payments.ts` got mixed up with this one, that's worth checking — but the nervousness is well-founded, because as a catalogue of hazards it's good. Here's what would bite, in blast-radius order.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-21

**Scope**: one file, 105 lines, 7 exported functions
**Verdict**: `purgeCanceledAccounts()` with no argument deletes every canceled account that has ever existed, silently, via raw SQL — fix that first; `transfer` is second.

## Findings

### 1. Purge with no argument deletes everything — Irreversible loss / Requires only forgetting
**Where**: `benchmarks/fixtures/payments.ts:80-88`
**Mistake**: Call `purgeCanceledAccounts()` — the obvious way to call it.
**Consequence**: `olderThan` defaults to *now*, so the cutoff is "before this instant" = all canceled accounts. Raw `DELETE` with no transaction, no dry-run, returns a count so it looks like it worked. Also string-interpolated SQL (`$executeRawUnsafe`) — safe today because it's an ISO string, a footgun the moment someone passes a string.
**Today**: None
**Device**: Make the cutoff required and bounded; use the parameterised client; delete by the IDs you just fetched, not a second predicate.
```ts
export async function purgeCanceledAccounts(olderThan: Date) {
  // poka-yoke: a cutoff in the last 30 days is almost certainly a mistake [control]
  if (olderThan > daysAgo(30)) throw new Error("cutoff too recent");
  const doomed = await db.accounts.findMany({ where: { status: "canceled", canceledAt: { lt: olderThan } } });
  await db.accounts.deleteMany({ where: { id: { in: doomed.map(a => a.id) } } });
  return doomed.length;
}
```
→ **Control**

### 2. Transfer is not atomic and the arguments are swappable — Money movement / Silent and plausible
**Where**: `:17-32`
**Mistake**: (a) Call `transfer(to, from, amt)` — two adjacent `string`s, compiles fine. (b) Two concurrent transfers from the same account both read balance, both pass the check, both write — funds created or destroyed. (c) Crash between the two `update`s: debit happened, credit didn't.
**Consequence**: Balance corruption with a successful-looking return value. No currency check either: USD debited, EUR credited at 1:1.
**Today**: None (the `from!` / `to!` assertions turn a missing account into a `TypeError` *after* nothing, but a missing `to` is caught only after `from` was already debited — no, actually before, but only by luck of ordering).
**Device**: Branded `AccountId`, a single object parameter, one transaction with atomic decrement and a guard in the `WHERE`.
```ts
type AccountId = string & { __brand: "AccountId" };
export async function transfer(p: { from: AccountId; to: AccountId; amount: Cents }) {
  return db.$transaction(async tx => {
    // poka-yoke: debit only succeeds if funds still suffice at write time [control]
    const r = await tx.accounts.updateMany({
      where: { id: p.from, balance: { gte: p.amount } },
      data: { balance: { decrement: p.amount } },
    });
    if (r.count === 0) throw new Error("insufficient funds");
    await tx.accounts.update({ where: { id: p.to }, data: { balance: { increment: p.amount } } });
  });
}
```
→ **Control**

### 3. Retry on a charge can double-bill, and failure returns `null` — Money movement / Silent
**Where**: `:44-60`
**Mistake**: Pass `retry = true` (or have a network timeout after Stripe created the charge).
**Consequence**: Stripe succeeded, the response was lost, the retry charges again. No idempotency key. And on failure the function returns `null`, so the caller gets a falsy "charge" and no error — `handleWebhook` ignores the return entirely.
**Today**: None
**Device**: Require an idempotency key, never catch-and-null.
```ts
await stripe.charges.create({ ... }, { idempotencyKey }); // poka-yoke: retry can't double-charge [control]
```
Drop the `catch`; let it throw. → **Control**

### 4. Webhook is unverified and drives a charge — Auth bypass → money / Reachable by anyone
**Where**: `:93-99`
**Mistake**: Accept a POST body from anyone. No signature check, `JSON.parse` of untrusted input, `event.data.amount` typed `any`.
**Consequence**: An attacker (or a replayed event) charges arbitrary customers arbitrary amounts. `invoice.paid` triggering a *new* charge is also semantically backwards — the invoice was already paid.
**Today**: None
**Device**: `stripe.webhooks.constructEvent(body, sig, secret)` before anything else; parse `event.data` through a schema. → **Control**

### 5. Boolean/positional parameter soup on `chargeCustomer` — Wrong output / Easy
**Where**: `:37-43`
**Mistake**: `chargeCustomer(id, 500, "usd", false, true)` — which flag is which? Also `amountCents: number` accepts `19.99` (dollars) with no complaint.
**Device**: Options object, `Cents` branded integer type validated at the boundary. → **Control**

### 6. `updateSubscription` writes status before checking it, and the switch falls through — Silent corruption
**Where**: `:67-78`
**Mistake**: Pass `"cancelled"` (two l's) or `"paused"`. The DB row gets the string anyway; the switch matches nothing; features stay whatever they were.
**Device**: `status: "active" | "canceled" | ...` union, exhaustive switch with `never` default, write *inside* the same branch as the side effect. → **Control**

### 7. `applyDiscount` accepts any number — Wrong output
**Where**: `:63-65`
**Mistake**: `percentOff = 0.2` (meaning 20%) or `150`. Returns a positive or negative price without complaint. Also runs on floats — fine for display, wrong for cents.
**Device**: Range assertion `0 ≤ percentOff ≤ 100`, integer-cents math with explicit rounding. → **Control**

### 8. Fire-and-forget receipt — Degraded / Silent
**Where**: `:52`
`void sendReceiptEmail(...)` — a rejection vanishes. Enqueue it or await it.

## Set aside
- `timeout` read from env and never used (`:95`) — dead code, not a hazard yet.
- `Account.currency`/`status` as bare `string` — covered by #2 and #6.

`★ Insight ─────────────────────────────────────`
Notice the ranking puts the `null`-returning catch in #3 *above* anything that crashes. A thrown error is cheap — someone sees it. A plausible wrong value (a `null` charge, a `0` count, a completed transfer with the wrong sign) compounds until an accountant finds it. That's why the audit skill orders by "silence × blast radius", not by how ugly the code looks.
`─────────────────────────────────────────────────`

**Recap**: `payments.ts` is the benchmark's deliberately booby-trapped fixture, not production code — check nothing real imports it. The eight hazards above are the ones it plants; the top three (unbounded raw-SQL purge, non-atomic swappable transfer, idempotency-free retry) are the money-losers. Per the audit skill I haven't edited anything; if you do want a real module hardened along these lines, point me at it and I'll apply the devices with the `// poka-yoke:` markers.