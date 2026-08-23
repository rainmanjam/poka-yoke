Write permission wasn't granted, so here it is in-conversation rather than at `docs/poka-yoke/audit-2026-08-22.md`.

## Verdict

**`handleWebhook` (line 93) is the one to fix before ship.** It `JSON.parse`s the body with no signature verification, then passes `event.data.customer` and `event.data.amount` straight into `chargeCustomer`. Anyone who can POST to that endpoint mints arbitrary charges against arbitrary customers. There's also no event-ID dedup, so a normal Stripe redelivery double-charges. Fix: `stripe.webhooks.constructEvent(rawBody, signature, secret)` — note it needs the **raw** body, so `body: string` is the wrong signature.

## The rest, by blast radius × ease

| # | Where | Mistake available | Consequence |
|---|---|---|---|
| 2 | `purgeCanceledAccounts:80` | Call it with no argument | `olderThan \|\| new Date()` makes the cutoff *now* — hard-deletes every canceled account ever. The most destructive behaviour is the default. |
| 3 | `transfer:17` | Pass a negative `amount` | `from.balance < -1000` is false, guard passes, debit becomes a credit. Unlimited money out of the destination account. |
| 4 | `chargeCustomer:55` | `retry = true` | A Stripe call that *succeeded but timed out* is re-issued with no idempotency key. Two valid charges, nothing reconciles them. |
| 5 | `transfer:25-32` | — (fails on its own) | Debit and credit are separate writes, no transaction. Second fails ⇒ money exists nowhere. `to` is also never null-checked before the debit runs. |
| 6 | `transfer:27` | Two concurrent transfers | Read-modify-write on `balance`: both read 100, both write 40, 120 left. Silent. Use `{ decrement: amount }` + a `CHECK (balance >= 0)`. |
| 7 | `chargeCustomer:59` | Ignore the return value | Catch swallows the error entirely — no log, no reason. Callers that fulfil on truthy ship goods free when Stripe hiccups. |
| 8 | `transfer:17` | `transfer(dst, src, amt)` | Two adjacent `string` params; compiler is happy. Also `Account.currency` is never compared — 100 EUR lands as 100 USD. |
| 9 | `updateSubscription:67` | Pass `"cancelled"` | Row updates, `switch` matches nothing, no `default` throws. Reads canceled, keeps full access. Revenue leak, zero errors. |
| 10 | `applyDiscount:63` | `applyDiscount(10, 100)` | Two swappable numbers; returns a plausible wrong number. `percentOff > 100` returns a **negative price**. |

Two extra aggravators inside #2: the `findMany` and the `DELETE` are independent queries with independently-evaluated predicates, so `doomed.length` **undercounts what was actually destroyed** — the number you'd put in the incident report is wrong. And it uses `$executeRawUnsafe` with interpolation.

**Set aside (7):** adjacent boolean params `sendReceipt`/`retry`; `currency = "usd"` default; floating `void sendReceiptEmail`; unused `WEBHOOK_TIMEOUT`; float money; stringly-typed `Account.status`/`currency`; the `from!`/`to!` assertions suppressing exactly the check that'd catch a bad ID.

One thing worth flagging: the detector script (`detect_hazards.py`) needed approval I couldn't grant, so this is hand-analysis only — the mechanical pass hasn't run.

★ Insight ─────────────────────────────────────
Notice the ranking puts #9 (silent state divergence) above a crash. That's deliberate per this repo's own doctrine: a loud failure is cheap, a plausible wrong answer compounds. `updateSubscription("cancelled")` succeeding is worse than it throwing.

Findings 3, 8 and 10 all collapse into *one* device — a branded `Money` type validated at construction. Three separate `if (amount <= 0) throw` guards would be Warning-rung; a type that can't hold a negative is Control-rung, because the next money function inherits it for free.
─────────────────────────────────────────────────

Want me to apply these? If so, a design call is yours to make: **should `transfer` reject a cross-currency transfer, or convert at a fetched rate?** Rejecting is Control-rung and trivial; converting means the FX rate, its staleness, and rounding direction all become part of the signature. I'd sketch the `Money` type and leave that branch for you.