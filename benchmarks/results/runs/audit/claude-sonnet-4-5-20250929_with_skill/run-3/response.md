Your gut was right to be nervous. I found **10 production-critical hazards** in this 105-line billing module, including:

**Critical (fix immediately)**:
1. **Transfer race condition** — two concurrent transfers can overdraw or lose money entirely (no transaction)
2. **Swappable account IDs** — `transfer(to, from, amt)` compiles and silently sends money backward
3. **Double-charging on retry** — timeout retry has no idempotency key
4. **Webhook signature not verified** — attacker can POST fake charges
5. **SQL injection** — raw string interpolation in DELETE query
6. **Unbounded purge** — `purgeCanceledAccounts()` with no args deletes EVERYTHING

**High (fix before production)**:
7. **Fire-and-forget receipts** — email failures vanish silently
8. **Boolean flag soup** — `chargeCustomer(id, 5000, "usd", false, true)` is unreadable at call site
9. **Stringly-typed status** — typos and new statuses silently fall through switch
10. **Money as float** — `0.1 + 0.2 ≠ 0.3`, compounds over time

The worst one is **#1** (transfer race) — two concurrent calls can both pass the balance check and overdraw, or lose a transfer mid-flight. No error, no alert — you find it in reconciliation days later.

I've written a full audit with proposed devices for each (transactions, branded types, idempotency keys, parameterized queries, etc.). The report shows the mistake, consequence, current protection (usually none), and the specific fix with code.

**docs/poka-yoke/audit-2026-08-20-payments-fixture.md** — want me to write it?