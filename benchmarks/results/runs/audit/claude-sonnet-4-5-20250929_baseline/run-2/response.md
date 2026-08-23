**STOP. This code has critical production hazards.** Here's what will bite you:

## 🔴 Critical (will cause data loss or financial damage)

**1. SQL Injection** (line 86-88)
```typescript
await db.$executeRawUnsafe(
  `DELETE FROM accounts WHERE status = 'canceled' AND canceled_at < '${cutoff.toISOString()}'`,
);
```
Template literals in `executeRawUnsafe` = direct SQL injection. Attacker-controlled `olderThan` can delete everything.

**2. Non-atomic transfers** (lines 25-32)
Two separate updates with no transaction. If the second fails, money vanishes from `fromAccount` but never reaches `toAccount`.

**3. Blind retry = double charging** (lines 56-58)
Retries on *any* error, including successful charges that failed to return. Customer gets charged twice.

**4. No webhook signature verification** (line 93-100)
Anyone can POST fake "invoice.paid" events to your endpoint and trigger arbitrary charges.

**5. Race condition in transfer** (lines 18-32)
Balance read at line 18, updated at line 25. Another transfer could drain the account in between, allowing overdraft.

## 🟡 High (dangerous defaults & silent failures)

**6. Dangerous purge default** (line 81)
```typescript
const cutoff = olderThan || new Date();
```
`purgeCanceledAccounts()` with no args deletes ALL canceled accounts immediately.

**7. Fire-and-forget receipts** (line 52)
```typescript
void sendReceiptEmail(customerId, charge.id);
```
Receipt failures are invisible. Customer charged but no confirmation.

**8. Floating-point money** (line 64)
```typescript
return price - price * (percentOff / 100);
```
JavaScript floats lose cents. $10.00 - 33% = $6.699999999

**9. Webhook double-charges** (line 98)
```typescript
if (event.type === "invoice.paid") {
  await chargeCustomer(event.data.customer, event.data.amount);
}
```
Invoice already paid by Stripe. This charges the customer a *second* time.

## 🟠 Medium (will break in production)

10. **Null assertions everywhere** (`from!.balance`, `to!.balance`) — crashes if account lookup returns null
11. **No currency validation** — can transfer USD to EUR accounts
12. **Unbounded status enum** — accepts any string, silent no-op on typos
13. **Argument swapping** — `transfer(from, to, amt)` easy to reverse

---

**Verdict:** This code will lose money, double-charge customers, and has an exploitable SQL injection. The comment says it's an "eval fixture" (line 1) — is this actually going to production, or is this a test harness?