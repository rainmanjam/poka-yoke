Quick flag before the audit itself: this file's header comment says it's a **benchmark eval fixture** — "Deliberately hazard-rich... every hazard here is one that ships in real codebases and passes review." It's not billing code that's actually headed to prod; it's a test fixture used to grade this skill's own detection accuracy (matches the `benchmarks/` results you have modified in git status). Worth confirming that's what you meant — if so, here's the audit as requested; if you meant a different file, point me at it.

Findings, ranked by blast radius × ease of mistake:

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-22

**Scope**: single file, 104 lines, named explicitly by user
**Verdict**: `handleWebhook` charges customers based on an unauthenticated request body — that's the one to fix first, everything else is second-order.

## Findings

### 1. Unverified webhook triggers real charges — Money movement+Auth bypass / Silent
**Where**: `payments.ts:93-100`
**Mistake**: Anyone who can reach this endpoint POSTs a fabricated `{"type":"invoice.paid","data":{"customer":"...","amount":...}}` body — no Stripe signature check exists.
**Consequence**: Arbitrary customer gets charged an arbitrary amount, chosen entirely by the caller. Looks like a normal successful charge; nothing distinguishes forged events from real ones.
**Today**: None.
**Device**: verify `stripe-signature` against the raw body before parsing → **Control**.
```ts
const sig = req.headers["stripe-signature"];
const event = stripe.webhooks.constructEvent(rawBody, sig, process.env.STRIPE_WEBHOOK_SECRET!);
// poka-yoke: forging this event would let anyone charge any customer [control]
```
Also unvalidated afterward: `event.data.amount` flows straight into `chargeCustomer` with no bound — even a legitimate-looking Stripe payload should be re-derived from your own invoice record, not trusted verbatim.

### 2. `chargeCustomer` retries without an idempotency key — Money movement / Silent
**Where**: `payments.ts:37-61`
**Mistake**: Any transient error (timeout, dropped response) triggers `chargeCustomer(..., retry=false)` — a second `stripe.charges.create` call with no idempotency key tying it to the first attempt.
**Consequence**: Double charge. Stripe has no way to know the second call is a retry of the first, so if the first charge actually succeeded but the response was lost, the customer is billed twice — silently, no error surfaces.
**Today**: None — worse, the `catch` swallows all errors and returns `null` either way, so a caller can't distinguish "charged twice," "charged once," and "not charged" without checking Stripe directly.
**Device**: pass a stable idempotency key (e.g. invoice/order ID) on every attempt → **Control**.
```ts
await stripe.charges.create(
  { customer: customerId, amount: amountCents, currency },
  { idempotencyKey: `charge:${customerId}:${invoiceId}` }, // poka-yoke: makes retries a no-op instead of a second charge [control]
);
```

### 3. `purgeCanceledAccounts()` with no argument deletes every canceled account — Irreversible data loss / Silent+easy
**Where**: `payments.ts:80-91`
**Mistake**: Call `purgeCanceledAccounts()` (the common, argument-free case) expecting it to purge *old* canceled accounts. `olderThan` defaults to `new Date()` — i.e. "now" — so the `canceledAt < cutoff` condition matches essentially every canceled account, not just aged ones.
**Consequence**: Full, unbounded, irreversible delete on a single omitted argument. Also runs via `$executeRawUnsafe` with a second, independently-built WHERE clause that can drift from the `findMany` above it — the returned count isn't guaranteed to match what was actually deleted.
**Today**: None.
**Device**: require the retention window explicitly, no default → **Control**.
```ts
export async function purgeCanceledAccounts(olderThan: Date) { // poka-yoke: no default — forces caller to choose the window [control]
  ...
  await db.accounts.deleteMany({ where: { status: "canceled", canceledAt: { lt: olderThan } } }); // parameterized, not string-built
}
```

### 4. `transfer` isn't atomic and doesn't validate `amount` — Money movement / Requires-unusual-input
**Where**: `payments.ts:17-35`
**Mistake**: Two sequential `db.accounts.update` calls with a read-then-write gap between them; nothing stops a concurrent transfer from reading stale balances (TOCTOU), and nothing rejects `amount <= 0` — a negative amount silently reverses the transfer's direction.
**Consequence**: Under concurrency, two simultaneous transfers can both pass the balance check and overdraw an account. A negative `amount` moves money the wrong way without error.
**Today**: None — the balance check (line 21) is the only guard, and it's already stale by the time the writes happen.
**Device**: wrap in a DB transaction with a row-level guard, and validate the sign → **Control**.
```ts
if (amount <= 0) throw new Error("amount must be positive");
await db.$transaction(async (tx) => {
  const from = await tx.accounts.findUniqueOrThrow({ where: { id: fromAccount } });
  if (from.balance < amount) throw new Error("insufficient funds");
  await tx.accounts.update({ where: { id: fromAccount }, data: { balance: { decrement: amount } } });
  await tx.accounts.update({ where: { id: toAccount }, data: { balance: { increment: amount } } });
});
```
Separately: `fromAccount`/`toAccount` are adjacent same-typed `string` params — a swapped call site compiles and runs, just reverses the transfer. Consider branded types (`AccountId`) so at least a wrong-shaped ID can't slip in; swap-proofing the order itself needs a named-args wrapper or object param.

### 5. `updateSubscription` silently no-ops on unrecognized status — Silent wrong state / Easy
**Where**: `payments.ts:67-78`
**Mistake**: `status` is a raw `string`. Any value besides exactly `"active"`/`"canceled"` (a typo, a new Stripe status like `"past_due"` or `"trialing"`) updates the DB row but the switch falls through — features are never enabled or disabled to match.
**Consequence**: DB and feature-access state diverge quietly; nothing errors, nothing logs.
**Today**: None.
**Device**: narrow `status` to a union and make the switch exhaustive → **Control**.
```ts
type SubStatus = "active" | "canceled" | "past_due" | "trialing";
function updateSubscription(subId: string, status: SubStatus) {
  switch (status) {
    case "active": ...
    case "canceled": ...
    case "past_due": ...
    case "trialing": ...
    default: { const _exhaustive: never = status; throw new Error(`unhandled: ${_exhaustive}`); } // poka-yoke: new status won't compile until handled [control]
  }
}
```

## Set aside
- `applyDiscount` doesn't clamp `percentOff` to 0-100 (a >100 value produces a negative price) — real, but low blast radius and easy to catch in a snapshot test. **Warning**-level, not worth a control here.
- `from!`/`to!` non-null assertions in `transfer` — subsumed by finding #4's rewrite (`findUniqueOrThrow` removes the need for the assertion).
- Unused `timeout` variable in `handleWebhook` — dead code, not a hazard.

Want me to write this to `docs/poka-yoke/audit-2026-08-22.md`, or apply any of these devices to the fixture directly?