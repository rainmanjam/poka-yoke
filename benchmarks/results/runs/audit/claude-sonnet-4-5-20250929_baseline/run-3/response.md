Hold on - I see this header:

```typescript
// Billing module — eval fixture.
// Deliberately hazard-rich, in ways that look like ordinary working code...
```

**This is a test fixture, not production code.** It's designed to contain hazards for evaluation purposes. Are you testing me, or did someone accidentally point you at the wrong file?

Either way, here's what would bite you if this *were* production:

★ **CRITICAL — Money Loss/Theft** ─────────────────

1. **Non-atomic transfer** (L25-32): Two separate updates with no transaction. If the credit fails, money vanishes into the void.
   - *Fix: Wrap in `db.$transaction()`*

2. **Double-charge on retry** (L56-57): Retries on ANY error, but if Stripe charged successfully and only the API response timed out, you charge twice.
   - *Fix: Check error type; only retry network failures, not `charge_succeeded` errors*

3. **SQL injection in purge** (L86-88): String interpolation in raw SQL. Attacker-controlled `cutoff` → full DB access.
   - *Fix: Use parameterized query or ORM*

4. **Webhook forgery** (L93-99): No signature verification. Attacker sends `{"type":"invoice.paid", "data":{"customer":"victim", "amount":999999}}` → you charge them.
   - *Fix: `stripe.webhooks.constructEvent(body, sig, secret)`*

5. **Webhook replay** (L98): No idempotency key. Stripe delivers webhooks 2-3x on retries → duplicate charges.
   - *Fix: Check `event.id` against processed events table*

★ **CRITICAL — Data Destruction** ────────────────

6. **Purge default = NOW** (L81): Calling `purgeCanceledAccounts()` with no args deletes EVERY canceled account instantly, not just old ones.
   - *Fix: Require the parameter or default to 90 days ago*

★ **MEDIUM — Silent Failures** ───────────────────

7. **Null on error** (L59): Returns `null` instead of throwing. Caller assumes success → no charge recorded.
   - *Fix: Let errors propagate*

8. **Fire-and-forget email** (L52): `void` swallows errors. Email fails → customer charged but no receipt, disputes spike.
   - *Fix: `await` it or log failures*

9. **Unbounded status** (L67-77): Accepts any string. Typo `"activ"` → features never enabled, money collected but service broken.
   - *Fix: Use union type `"active" | "canceled" | ...`*

10. **Float money** (L12, L63): `balance: number` → 0.1 + 0.2 = 0.30000000000000004. Rounding errors accumulate.
    - *Fix: Store cents as integers*

★ **MEDIUM — Design Hazards** ────────────────────

11. **Swappable args** (L17): Both strings, easy to reverse → money flows backward.
    - *Fix: Branded types or object param `{from, to, amount}`*

12. **Null assertions** (L21, L27, L31): `from!.balance` crashes if account not found.
    - *Fix: `if (!from) throw` before using*

───────────────────────────────────────────────────

**If this were real billing code going to prod**, I'd block the deploy until #1-6 are fixed. The others are bugs waiting to happen but won't immediately steal money.

What's the actual file you want reviewed?