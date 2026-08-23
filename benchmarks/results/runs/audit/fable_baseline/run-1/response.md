The write was declined, so here's the audit inline.

**First, the thing that should make you nervous most:** `payments.ts:1-4` literally says "eval fixture — deliberately hazard-rich… every hazard here is one that ships in real codebases and passes review." If this is what's headed to production, that's the headline. Assuming you want the hazards enumerated anyway, ranked by blast radius × ease:

1. **`purgeCanceledAccounts()` with no arg deletes every canceled account** (`:80-88`). `olderThan || new Date()` makes the cutoff *now*. Returns a count, no error. Also raw SQL via string interpolation. Device: required `olderThan`, reject future dates, use `deleteMany` with the same `where` as the find → Control.

2. **`transfer` isn't atomic** (`:17-35`). Two reads, then two writes, no transaction. Concurrent calls race past the balance check; a crash between updates debits without crediting. Device: one transaction, `decrement`/`increment`, conditional debit `where: { id, balance: { gte: amount } }` → Control.

3. **`transfer(to, from, amt)` compiles and succeeds** (`:17`). Two adjacent strings. Device: branded `AccountId` + object param `{ from, to, amount }` → Control.

4. **Amount units and signs are unchecked** (`:17, :39, :63`). `amountCents = 19.99`, negative `amount` (reverses the transfer and skips the balance check), `percentOff = 0.2`. Device: `Cents` branded integer, positive-int assertion at the boundary, `Percent` type bounded 0–100 → Control.

5. **`chargeCustomer` swallows errors and retries without idempotency** (`:44-60`). Returns `null` on failure (callers proceed as paid); `retry=true` after a timeout can charge twice. Device: throw; Stripe `idempotencyKey` from the business event; drop the `retry` flag → Control.

6. **Webhook is unverified** (`:93-99`). `JSON.parse` of raw body, no signature check, then charges whoever the body names. `WEBHOOK_TIMEOUT` is read and ignored. Device: `stripe.webhooks.constructEvent` + schema-parse → Control.

7. **Five positional params, three boolean/defaulted** (`:37-43`). `(id, 500, "eur", false)` — did that disable receipts or retries? Device: options object → Control.

8. **Stringly status + non-exhaustive switch** (`:14, :67-78`). `"cancelled"` updates the row and silently does nothing else. Device: union type, `assertNever` default, and put the DB write inside each branch → Control.

**Set aside:** `from!`/`to!` non-null assertions (crash loudly — cheap failure, but will matter after #2), `void sendReceiptEmail` dropping a promise (`no-floating-promises`), unvalidated `currency`.

**Recap:** eight mistake affordances, all currently at rung None; #1 and #2 are the ones that lose money or data irreversibly. I haven't changed any code — if you want the report file or the fixes applied, say which and I'll do it.