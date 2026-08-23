I'll perform a thorough manual audit using the three poka-yoke lenses. Let me analyze the payments module.

★ Insight ─────────────────────────────────────
This is a billing module—the highest-risk surface in any codebase. Money movement, retries, and webhooks are where silent mistakes become expensive and public incidents. I'll apply all three lenses (Contact, Fixed-value, Motion-step) systematically.
─────────────────────────────────────────────────

# Poka-Yoke Audit — benchmarks/fixtures/payments.ts — 2026-08-20

**Scope**: Single file, 105 lines, payments/billing module  
**Verdict**: **Non-atomic transfer and retry-without-idempotency are production-destroying hazards.** Fix those two first.

## Findings

### 1. Non-atomic money transfer — **Critical** / **Easy**
**Where**: `benchmarks/fixtures/payments.ts:17-35`  
**Mistake**: A failure between the two `update` calls leaves money deducted from one account but never credited to the other. Retry logic or a crash creates permanent loss.  
**Consequence**: **Silent data corruption.** The system's total balance no longer sums to what it should. Reconciliation catches it days later after hundreds of transactions have compounded the error.  
**Today**: **None**  
**Device**: Wrap both updates in a database transaction → **Control**

```ts
export async function transfer(fromAccount: string, toAccount: string, amount: number) {
  return await db.$transaction(async (tx) => {
    const from = await tx.accounts.findUnique({ where: { id: fromAccount } });
    const to = await tx.accounts.findUnique({ where: { id: toAccount } });

    if (!from || !to) throw new Error("account not found");
    if (from.balance < amount) throw new Error("insufficient funds");

    await tx.accounts.update({
      where: { id: fromAccount },
      data: { balance: from.balance - amount },
    });
    await tx.accounts.update({
      where: { id: toAccount },
      data: { balance: to.balance + amount },
    });

    return { from: fromAccount, to: toAccount, amount };
  });
}
```

*Control would also need optimistic locking or `SELECT FOR UPDATE` to prevent lost updates under concurrent transfers—the current version has a check-then-act race (M5).*

---

### 2. Swappable account IDs — **Critical** / **Trivial**
**Where**: `benchmarks/fixtures/payments.ts:17`  
**Mistake**: Call `transfer(toAccount, fromAccount, 1000)` with arguments reversed. Compiles, passes review, moves money the wrong direction.  
**Consequence**: **Immediate financial loss.** User reports "I was charged instead of paid." The transaction is in the database as correct-looking data.  
**Today**: **None**  
**Device**: Branded types for `SourceAccount` and `DestAccount` so swapping them is a compile error → **Control**

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

type SourceAccountId = Brand<string, "SourceAccount">;
type DestAccountId = Brand<string, "DestAccount">;

export async function transfer(
  from: SourceAccountId,
  to: DestAccountId,
  amount: number
) {
  // implementation
}
```

*Alternatively: force named arguments via an options object, which is **Warning** rung but nearly free.*

---

### 3. Retry doubles the charge — **Critical** / **Easy**
**Where**: `benchmarks/fixtures/payments.ts:44-60`  
**Mistake**: A transient Stripe error triggers the retry branch. The first charge succeeded but Stripe's response timed out. The retry creates a second charge.  
**Consequence**: **Customer double-charged.** Highly visible, requires manual refund, damages trust. This is the canonical payment hazard.  
**Today**: **None** — the retry has no idempotency key  
**Device**: Required idempotency key parameter, passed to Stripe → **Control**

```ts
export async function chargeCustomer(
  customerId: string,
  amountCents: number,
  idempotencyKey: IdempotencyKey,  // required, not optional
  currency = "usd",
  sendReceipt = true,
) {
  const charge = await stripe.charges.create({
    customer: customerId,
    amount: amountCents,
    currency,
    idempotency_key: idempotencyKey,  // Stripe native support
  });

  if (sendReceipt) {
    await sendReceiptEmail(customerId, charge.id);
  }
  return charge;
}
```

*Removing the retry logic entirely is also valid—Stripe SDK has built-in retries with exponential backoff and idempotency.*

---

### 4. Missing webhook signature verification — **Critical** / **Moderate**
**Where**: `benchmarks/fixtures/payments.ts:93-100`  
**Mistake**: An attacker POSTs `{"type": "invoice.paid", "data": {"customer": "...", "amount": 999999}}` directly to your webhook endpoint.  
**Consequence**: **Arbitrary charges created.** No authentication means anyone who discovers the URL can trigger financial operations.  
**Today**: **None**  
**Device**: Verify `stripe-signature` header before processing → **Control**

```ts
export async function handleWebhook(body: string, signature: string, secret: string) {
  const event = stripe.webhooks.constructEvent(body, signature, secret);
  // constructEvent throws if signature invalid—no processing happens
  
  if (event.type === "invoice.paid") {
    await chargeCustomer(event.data.object.customer, event.data.object.amount, ...);
  }
}
```

---

### 5. Fire-and-forget receipt email — **High** / **Easy**
**Where**: `benchmarks/fixtures/payments.ts:52`  
**Mistake**: The email send fails or the process exits before it completes. The `void` cast makes the error invisible.  
**Consequence**: **Customer never receives receipt.** Silent—no log, no alert. Customer support learns about it weeks later.  
**Today**: **None**  
**Device**: Await the email send, or move it to a queue; enable `no-floating-promises` lint rule → **Warning**

```ts
if (sendReceipt) {
  await sendReceiptEmail(customerId, charge.id);  // or enqueue
}
```

*Awaiting inline makes the charge slower; a proper device is an outbox pattern or job queue, but awaiting is the 5-minute fix that prevents silent loss.*

---

### 6. Swallowed errors return null — **High** / **Easy**
**Where**: `benchmarks/fixtures/payments.ts:55-60`  
**Mistake**: Stripe rejects the charge (card declined, fraud check, account issue). The catch block returns `null`. The caller doesn't check for null or treats it as success.  
**Consequence**: **Order fulfilled with no payment.** The failure is silent at the point it happens; the discrepancy surfaces in reconciliation days later.  
**Today**: **None**  
**Device**: Let the error propagate, or return a discriminated union → **Control**

```ts
type ChargeResult =
  | { status: "success"; charge: Stripe.Charge }
  | { status: "failed"; reason: string };

export async function chargeCustomer(...): Promise<ChargeResult> {
  try {
    const charge = await stripe.charges.create({...});
    return { status: "success", charge };
  } catch (e) {
    return { status: "failed", reason: e.message };
  }
}
```

*Returning null converts a loud failure into a quiet wrong assumption—the exact opposite of mistake-proofing.*

---

### 7. SQL injection in purge — **Critical** / **Moderate**
**Where**: `benchmarks/fixtures/payments.ts:86-88`  
**Mistake**: `olderThan` comes from user input (query param, admin panel date picker). Injecting `'; DROP TABLE accounts; --` is now possible.  
**Consequence**: **Database compromise.** In a deletion function, which makes it extra dangerous.  
**Today**: **None**  
**Device**: Use parameterized query or ORM method → **Control**

```ts
await db.$executeRaw`
  DELETE FROM accounts 
  WHERE status = 'canceled' AND canceled_at < ${cutoff}
`;
// or better: use the ORM
await db.accounts.deleteMany({
  where: { status: "canceled", canceledAt: { lt: cutoff } }
});
```

---

### 8. Unbounded account purge — **High** / **Easy**
**Where**: `benchmarks/fixtures/payments.ts:80-91`  
**Mistake**: Call `purgeCanceledAccounts()` with no argument, or a far-future date. The default `new Date()` matches **all** canceled accounts regardless of age.  
**Consequence**: **Mass deletion.** The function name says "old" but the behavior is "all." Irreversible.  
**Today**: **None**  
**Device**: Make `olderThan` required, or add a row-count cap → **Control**

```ts
export async function purgeCanceledAccounts(olderThan: Date) {
  // no default—caller must decide the cutoff
  
  // Alternatively: add a guard
  if (doomed.length > 1000) {
    throw new Error(`Refusing to delete ${doomed.length} accounts. Add explicit confirm flag.`);
  }
}
```

---

### 9. Stringly-typed status field — **Medium** / **Easy**
**Where**: `benchmarks/fixtures/payments.ts:14, 67-77`  
**Mistake**: Set `status = "actve"` (typo). Compiles. The subscription is in an undefined state and the switch falls through to... nothing.  
**Consequence**: **Features never enabled.** Silent—the status update succeeds, the feature toggle doesn't happen.  
**Today**: **Detection** (assuming there's a test)  
**Device**: Literal union type + exhaustive switch → **Control**

```ts
export type SubscriptionStatus = "active" | "canceled" | "trialing" | "past_due";

export interface Account {
  id: string;
  status: SubscriptionStatus;
  // ...
}

export async function updateSubscription(subId: string, status: SubscriptionStatus) {
  await db.subscriptions.update({ where: { id: subId }, data: { status } });

  switch (status) {
    case "active":
      await enableFeatures(subId);
      break;
    case "canceled":
      await disableFeatures(subId);
      break;
    case "trialing":
    case "past_due":
      // explicit handling
      break;
    default:
      // @ts-expect-error - exhaustiveness check
      const _exhaustive: never = status;
      throw new Error(`Unhandled status: ${_exhaustive}`);
  }
}
```

---

### 10. Money as a float — **Medium** / **Easy**
**Where**: `benchmarks/fixtures/payments.ts:12, 39, 63`  
**Mistake**: `balance: number` means `0.1 + 0.2 !== 0.3`. Accumulates over time, breaks reconciliation.  
**Consequence**: **Accounting drift.** Pennies lost per transaction, thousands of dollars annually, impossible to trace.  
**Today**: **None**  
**Device**: Integer cents + Money type that carries currency → **Control**

```ts
type Brand<T, B> = T & { readonly [brand]: B };
type Cents = Brand<number, "Cents">;

export interface Money {
  amountCents: Cents;
  currency: string;
}

export interface Account {
  id: string;
  balance: Money;  // not `number`
}
```

---

### 11. Dangerous boolean flag defaults — **Medium** / **Trivial**
**Where**: `benchmarks/fixtures/payments.ts:40-42`  
**Mistake**: Call `chargeCustomer(id, 5000)` without thinking. Gets `sendReceipt=true` and `retry=false`—one is invisible, the other makes the call site unreadable.  
**Consequence**: **Unintended behavior.** The retry flag especially—boolean parameters are invisible at call sites.  
**Today**: **None**  
**Device**: Options object with named fields, or remove retry entirely → **Warning**

```ts
export async function chargeCustomer(
  customerId: string,
  amountCents: number,
  options: {
    currency?: string;
    sendReceipt?: boolean;
    idempotencyKey: string;  // required
  }
) {
  // retry removed—Stripe SDK handles that
}
```

---

### 12. Missing null checks / non-null assertions — **Medium** / **Moderate**
**Where**: `benchmarks/fixtures/payments.ts:21, 27, 31`  
**Mistake**: `findUnique` returns `null` if account doesn't exist. The `!` assertion crashes if the ID is wrong.  
**Consequence**: **500 error instead of 400.** Correct behavior (reject invalid ID) but wrong status code and poor error message.  
**Today**: **Warning** (crashes, which is loud)  
**Device**: Explicit null check with a descriptive error → **Control**

```ts
const from = await db.accounts.findUnique({ where: { id: fromAccount } });
const to = await db.accounts.findUnique({ where: { id: toAccount } });

if (!from) throw new Error(`Source account ${fromAccount} not found`);
if (!to) throw new Error(`Destination account ${toAccount} not found`);
```

---

### 13. Unused webhook timeout config — **Low** / **N/A**
**Where**: `benchmarks/fixtures/payments.ts:95`  
**Mistake**: `timeout` is read but never used. Someone added it expecting it to do something.  
**Consequence**: **False confidence.** The config suggests timeouts are enforced; they aren't.  
**Today**: **None**  
**Device**: Either use it or delete the line → **Control**

---

## Set aside

5 lower-priority issues:

- `applyDiscount` returns fractional cents (line 63-65) — fine for display, wrong for storage
- `currency` parameter has a default but no validation — "foo" is accepted
- Missing index on `(status, canceledAt)` makes the purge query slow at scale
- No logging on financial operations makes incident investigation painful
- Async functions have no timeout — a stuck Stripe call blocks forever

---

## Recommendations

**Ship-blocking (fix before production):**
1. Wrap `transfer` in a transaction (#1)
2. Add required idempotency key to `chargeCustomer` (#3)
3. Verify webhook signatures (#4)
4. Fix SQL injection in `purgeCanceledAccounts` (#7)

**High-priority (fix this sprint):**
5. Branded account IDs (#2)
6. Remove error swallowing, return discriminated union (#6)
7. Guard unbounded purge (#8)
8. Literal union for status + exhaustive check (#9)

**Medium-priority (next sprint):**
9. Await receipt email or move to queue (#5)
10. Money type with integer cents (#10)
11. Options object instead of boolean flags (#11)

**Low-priority:**
12. Explicit null checks (#12)
13. Delete unused timeout (#13)

Would you like me to write this audit to `docs/poka-yoke/audit-2026-08-20.md`, or would you prefer to discuss which devices to apply first?