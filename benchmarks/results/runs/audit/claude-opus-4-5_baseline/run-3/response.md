Your instincts are right — this file has several hazards that could cause real financial damage. Here's what I found:

---

## Critical Issues

**1. Money can vanish — `transfer()` has no transaction** (lines 25-32)
If the second `update` fails after the first succeeds, the debit happens but the credit doesn't. The money disappears. These two operations need to be wrapped in a database transaction.

**2. SQL injection — `purgeCanceledAccounts()`** (line 87)
```typescript
`DELETE FROM accounts WHERE ... canceled_at < '${cutoff.toISOString()}'`
```
Direct string interpolation into raw SQL. If `olderThan` ever comes from user input, this is exploitable.

**3. Double-charging customers — `handleWebhook()`** (line 98)
When `invoice.paid` fires, you're calling `chargeCustomer()` again. The invoice is *already* paid — this charges them a second time.

**4. No webhook signature verification** (line 94)
Anyone can POST a fake Stripe event to your endpoint. Without `stripe.webhooks.constructEvent()` verification, attackers can trigger arbitrary billing actions.

---

## High-Risk Issues

**5. Silent charge failures — `chargeCustomer()` returns `null`** (line 59)
Failed charges return `null` instead of throwing. Callers that don't explicitly check for null will think the charge succeeded.

**6. Floating-point money — `applyDiscount()`** (lines 63-65)
`price * (percentOff / 100)` produces values like `19.999999999999996`. Use integer cents throughout, or a decimal library.

**7. Non-null assertions on nullable data — `transfer()`** (lines 21, 27, 28, 31)
`from!.balance` crashes if the account doesn't exist, instead of returning a helpful "account not found" error.

**8. No idempotency in webhook handler** (lines 93-100)
Stripe retries webhooks. Without tracking processed event IDs, duplicate deliveries cause duplicate charges.

---

## Medium Issues

**9. Default purges everything** (line 81)
If `olderThan` is undefined, `cutoff = new Date()` deletes ALL canceled accounts, including ones canceled 1 second ago. This should probably require an explicit date.

**10. Switch without default case — `updateSubscription()`** (lines 70-77)
Statuses like `"paused"`, `"past_due"`, `"trialing"` fall through silently. Features stay in whatever state they were — probably not intended.

**11. Unused variable** (line 95)
`timeout` is read from env but never used. Dead code or forgotten implementation?

---

`★ Insight ─────────────────────────────────────`
The scariest pattern here is *silent failures that look like success*. The `chargeCustomer` returning `null`, the switch with no default, the fire-and-forget email — these don't crash, so they pass tests and reviews. But in production, customers don't get charged, subscriptions don't update, and nobody knows until revenue reports look wrong.
`─────────────────────────────────────────────────`

**Bottom line:** The transaction gap in `transfer()` and the double-charge bug in `handleWebhook()` are ship-blockers. The SQL injection is a security blocker. Want me to draft fixes for any of these?