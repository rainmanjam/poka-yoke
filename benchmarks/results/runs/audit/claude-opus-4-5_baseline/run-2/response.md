Your instincts are right. This file has several hazards that would pass a casual review but could cause real money problems:

`★ Insight ─────────────────────────────────────`
Billing code has a unique failure mode: bugs that pass tests, pass review, and work correctly 99.9% of the time — then silently lose money at scale. The hazards below all share that signature.
`─────────────────────────────────────────────────`

**Critical (money loss/security):**

| Line | Hazard | What bites you |
|------|--------|----------------|
| 25-32 | **No transaction around transfer** | If the second `update` fails (network blip, constraint violation), money vanishes — debited from `from` but never credited to `to`. Needs `db.$transaction()`. |
| 86-88 | **SQL injection via `$executeRawUnsafe`** | Date interpolation looks safe but the pattern invites copy-paste disasters. Also: calling `purgeCanceledAccounts()` with no args defaults `cutoff` to *now*, deleting ALL canceled accounts. |
| 93-99 | **Webhook without signature verification** | `JSON.parse(body)` trusts any POST. Attackers can forge `invoice.paid` events to trigger charges. Must verify `stripe-signature` header. |

**High (silent failures):**

| Line | Hazard | What bites you |
|------|--------|----------------|
| 55-60 | **`chargeCustomer` returns `null` on failure** | Callers can't distinguish success from silent failure. A failed charge looks like success to upstream code. |
| 70-77 | **Incomplete switch on `status`** | Only handles `active`/`canceled`. Statuses like `past_due`, `paused`, `trialing` silently do nothing — features stay enabled for non-paying users. |

**Medium (correctness):**

| Line | Hazard | What bites you |
|------|--------|----------------|
| 64 | **Floating-point on money** | `price * (percentOff / 100)` produces float errors. `$99.99 * 0.1 = 9.998999...`. Use integer cents. |
| 21, 27-28 | **Non-null assertions `from!`, `to!`** | If either account doesn't exist, runtime crash instead of graceful error. |
| 95 | **Unused `timeout` variable** | Read from env, never used — dead code or missing timeout logic. |

**The one that would wake me up at 3am:** The transfer race condition (lines 25-32). Under load, you *will* have partial transfers that pass all your tests and only show up as customer complaints weeks later when reconciliation fails.

Want me to show the fix for any of these?