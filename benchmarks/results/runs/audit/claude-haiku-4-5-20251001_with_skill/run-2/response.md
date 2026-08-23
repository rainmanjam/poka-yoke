Let me conduct the audit manually using the three lenses. I'll analyze the code for the hazards that typically appear in billing systems.

**Scope**: `benchmarks/fixtures/payments.ts` — a billing/payment module (105 lines)

Based on reading the code and applying the three inspection lenses (Contact, Fixed-value, Motion-step), here are the critical findings:

## Poka-Yoke Audit — payments.ts — 2026-08-22

**Verdict**: Five reversible-damage hazards that could charge customers incorrectly or leak money, with no runtime guardrails. Priority: idempotency keys + DB constraints + server-side validation.

### Findings

**1. Missing idempotency keys allows duplicate charges — Critical / Easy**
**Where**: `chargeCustomer()` lines 37–61
**Mistake**: A network timeout or retry causes `chargeCustomer()` to be called twice with identical parameters; Stripe charges twice but the code treats it as one.
**Consequence**: Customers charged twice (silent money movement, discovered only by customer complaint or reconciliation job).
**Today**: None — no idempotency key in Stripe request, no DB constraint preventing duplicates.
**Device**: Add idempotency key (order ID or similar) to Stripe call + unique DB constraint — **Control**

```typescript
// Add to chargeCustomer signature:
idempotencyKey: string  // typically an order ID

// Pass to Stripe:
const charge = await stripe.charges.create({
  customer: customerId,
  amount: amountCents,
  currency,
  idempotency_key: idempotencyKey,  // prevents duplicate charges server-side
});
```

---

**2. Transfer function is non-atomic — Blast radius: Medium / Medium**
**Where**: `transfer()` lines 17–35
**Mistake**: After deducting from `fromAccount`, if the second update fails, the first is already committed; money vanishes (from perspective is debited, to perspective doesn't credit).
**Consequence**: Silent ledger hole. Two separate DB updates = between-state exposure.
**Today**: None — nothing enforces atomicity.
**Device**: Wrap both updates in a transaction — **Control**

```typescript
await db.$transaction([
  db.accounts.update({
    where: { id: fromAccount },
    data: { balance: from!.balance - amount },
  }),
  db.accounts.update({
    where: { id: toAccount },
    data: { balance: to!.balance + amount },
  }),
]);
```

---

**3. Webhook handler does not validate signature — Blast radius: Critical / Easy**
**Where**: `handleWebhook()` lines 93–100
**Mistake**: Parse and charge based on JSON body without verifying it came from Stripe (no HMAC signature check). Attacker sends `{type: "invoice.paid", data: {customer: "...", amount: 99999}}` and the server charges that customer.
**Consequence**: Unauthorized charges (money movement from valid customer, no authorization).
**Today**: None — signature validation is missing entirely.
**Device**: Verify HMAC signature before parsing body — **Control**

```typescript
export async function handleWebhook(body: string, signature: string) {
  const isValid = stripe.webhooks.constructEvent(body, signature, process.env.STRIPE_WEBHOOK_SECRET);
  if (!isValid) throw new Error("Invalid signature");
  const event = isValid;
  // … rest of handler
}
```

---

**4. Money stored as float instead of integer cents — Blast radius: Medium / Hard**
**Where**: `Account.balance` line 12, `transfer()` line 27, `applyDiscount()` line 63–65
**Mistake**: Floating-point arithmetic on money (balance: number, price: number). A discount of 33.33% leaves a fractional cent; cumulative rounding errors silently create ledger discrepancies.
**Consequence**: Silent financial mismatch (€0.01 here × 10M transactions = €100K loss, undetected by non-exact-match audits).
**Today**: None — no type enforcement, balances freely become decimals.
**Device**: Use `Decimal` type or store as integers (cents/smallest unit) — **Control**

```typescript
// Better:
export interface Account {
  balance: BigInt;  // stored in cents, never floats
  currency: string;
}

// Or use a library:
import Decimal from "decimal.js";
export interface Account {
  balance: Decimal;  // enforces exact arithmetic
}
```

---

**5. Unguarded DELETE query with user-controlled date — Blast radius: High / Medium**
**Where**: `purgeCanceledAccounts()` lines 80–91
**Mistake**: SQL injection: `olderThan` date is interpolated directly into SQL string without parameterization. A caller passing `olderThan = "2020-01-01' OR '1'='1"` deletes *all* canceled accounts, not just old ones.
**Consequence**: Unintended bulk deletion (irreversible data loss).
**Today**: None — raw SQL string interpolation, no parameterization.
**Device**: Use parameterized query (already available via Prisma DSL) — **Control**

```typescript
// Current (BROKEN):
`DELETE FROM accounts WHERE status = 'canceled' AND canceled_at < '${cutoff.toISOString()}'`

// Fixed:
await db.accounts.deleteMany({
  where: { status: "canceled", canceledAt: { lt: cutoff } },
});
```

---

**6. Retry loop can retry indefinitely on network error — Blast radius: Medium / Medium**
**Where**: `chargeCustomer()` lines 56–58
**Mistake**: `retry` boolean doesn't track retry count. A timeout in the catch block re-calls with `retry=false`, so only one retry. But if the caller wraps this in their own retry loop (common pattern), you get exponential retry storms.
**Consequence**: Retry amplification (network storm), potential for double-charge if Stripe partially processes the first retry before timing out.
**Today**: Warning — the single-retry does limit damage, but pattern is fragile.
**Device**: Replace boolean with retry count limit, or remove retry logic and let caller control — **Control**

```typescript
export async function chargeCustomer(
  customerId: string,
  amountCents: number,
  currency = "usd",
  sendReceipt = true,
  retryCount = 1,
) {
  try {
    // …
  } catch (e) {
    if (retryCount > 0) {
      return chargeCustomer(customerId, amountCents, currency, sendReceipt, retryCount - 1);
    }
    return null;
  }
}
```

---

**7. Unexhaustive switch on subscription status — Blast radius: Low / High**
**Where**: `updateSubscription()` lines 70–77
**Mistake**: Adding a new subscription status (e.g., `"past_due"`, `"suspended"`) doesn't trigger a TypeScript error because the switch has no `default` case requiring exhaustiveness. Code silently skips the new status.
**Consequence**: Features silently stay enabled/disabled for new statuses (degraded UX or security issue depending on status).
**Today**: Warning — TypeScript allows this, but the bug is silent.
**Device**: Add `default` case or use exhaustiveness checker — **Warning**

```typescript
switch (status) {
  case "active":
    await enableFeatures(subId);
    break;
  case "canceled":
    await disableFeatures(subId);
    break;
  default:
    throw new Error(`Unknown subscription status: ${status}`);
}
```

---

**8. Unsafe JSON.parse on webhook body — Blast radius: Medium / Easy**
**Where**: `handleWebhook()` line 94
**Mistake**: Malformed JSON crashes the handler (DoS). Even if caught upstream, the error propagates silently in line 59 (catch returns null).
**Consequence**: Webhook silently fails to charge; customer sees no error, payment appears not to go through, potentially double-charges when they retry manually.
**Today**: None — no try-catch around parse, crashes unobserved.
**Device**: Validate JSON structure + log parse errors — **Warning**

```typescript
try {
  const event = JSON.parse(body);
  // … validate event.type, event.data exist
} catch (e) {
  console.error("Webhook parse error:", e);
  throw new Error("Invalid webhook body");
}
```

---

**9. No validation of webhook data before charging — Blast radius: High / Medium**
**Where**: `handleWebhook()` lines 97–99
**Mistake**: Trust `event.data.customer` and `event.data.amount` without checking they exist or are the right type. A malformed webhook `{type: "invoice.paid", data: {}}` calls `chargeCustomer(undefined, undefined)`.
**Consequence**: Wrong customer charged, or charge with amount=`undefined` (NaN in math, fails silently).
**Today**: None — no schema validation on webhook body.
**Device**: Validate webhook structure against expected schema — **Control**

```typescript
const schema = z.object({
  type: z.literal("invoice.paid"),
  data: z.object({
    customer: z.string(),
    amount: z.number().int().positive(),
  }),
});
const validated = schema.parse(JSON.parse(body));
await chargeCustomer(validated.data.customer, validated.data.amount);
```

---

## Set aside
- **Insufficient funds check is non-atomic** (balance changes between check and update) — requires row-level locking, expensive to fix, lower priority than transfer atomicity.
- **sendReceiptEmail is fire-and-forget without tracking** — email can fail silently; low blast radius but worth monitoring in production.

---

**Summary**: This code has **5 critical findings** (idempotency, atomicity, webhook signature, SQL injection, money as float) that could cause financial loss. Three are Control-level (type system, schema validation, DB constraints); one is just missing. All are common in production billing code and all have low-cost fixes that prevent entire categories of mistakes.

Ready to propose fixes?