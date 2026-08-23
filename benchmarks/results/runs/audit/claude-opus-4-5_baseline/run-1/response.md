Your instincts are right — this file has several hazards that would pass most reviews but could cause real production incidents. Here's what I found, ranked by blast radius:

---

## Critical — will lose money or data

**1. Non-atomic transfer (lines 25-32)**
Two separate `UPDATE` calls without a transaction. If the second fails (network blip, constraint violation), the source account is debited but the destination never credited. Money vanishes.

**2. Double-charging customers (line 98)**
`invoice.paid` means Stripe *already collected payment*. Calling `chargeCustomer()` here charges them **again**. This is the kind of bug that generates chargebacks and angry support tickets.

**3. No webhook signature verification (line 94)**
Anyone can POST a crafted JSON body and trigger charges. Stripe webhooks must verify `stripe-signature` header — without it, this is an open fraud vector.

**4. Silent charge failures (lines 55-60)**
Catches all errors and returns `null`. Failed charges disappear silently — no logging, no alerting, no audit trail. You won't know revenue is leaking until the monthly reconciliation.

---

## High — dangerous defaults

**5. Purge defaults to NOW (line 81)**
`olderThan || new Date()` means calling `purgeCanceledAccounts()` with no argument deletes **all** canceled accounts. One missing parameter = mass data loss.

**6. SQL injection pattern (line 87)**
`$executeRawUnsafe` with string interpolation. Even if `toISOString()` is safe today, this pattern invites future injection bugs.

**7. Unbounded subscription status (line 67)**
`status: string` accepts anything. The switch only handles `"active"` and `"canceled"` — other states like `"past_due"` or `"paused"` fall through silently. No features get disabled, no error thrown.

---

## Medium — correctness issues

**8. No discount bounds (line 64)**
`percentOff` could be 150 (negative price) or -20 (price increase). No validation.

**9. Floating-point money (line 64)**
`price * (percentOff / 100)` introduces rounding errors that accumulate. Use integer cents throughout.

**10. Fire-and-forget receipt (line 52)**
`void sendReceiptEmail(...)` — if it fails, nobody knows. May have compliance implications.

---

`★ Insight ─────────────────────────────────────`
The scariest hazards here are the ones that *look* correct: the `invoice.paid` handler looks like it's doing the right thing, the default argument on `purgeCanceledAccounts` looks helpful, the try/catch looks like error handling. These pass review because reviewers pattern-match "I see error handling" without tracing what actually happens on failure.
`─────────────────────────────────────────────────`

---

Want me to sketch fixes for the critical ones? The transfer needs a transaction wrapper, the webhook needs `stripe.webhooks.constructEvent()`, and the `invoice.paid` handler should probably just record the payment rather than initiate a new charge.