Your interim fix is **not sufficient** — it's a Warning (rung 2) with a critical TOCTOU race that still allows double-charges, and it only patches one code path when the hazard is system-wide.

Let me walk through this using the retro method:

## **The three things**

**Defect**: 340 customers charged twice (~2nd occurrence)  
**Mistake**: Queue redelivered a message after Stripe timeout; payment worker processed both attempts  
**Hazard**: **Stripe charges lack idempotency keys** (either not passed at all, or optional in your Stripe integration). This makes duplicate charges possible and silent — charge succeeds both times, returns different transaction IDs.

## **Why your amount-based check fails**

```
Check for recent charge with amount X
    ↓ [microsecond delay/async race]
    ↓ [parallel request arrives]
    ↓ Charge again
    ↓
Second charge succeeds
```

This is a **time-of-check to time-of-use (TOCTOU) race**. Also: legitimate customers *do* get charged twice sometimes (subscription renewal + manual purchase). Amount matching will produce false negatives.

## **The real root cause: queue-wide idempotency gap**

The problem isn't just the payment worker. Your queue (SQS/RabbitMQ/etc) redelivers on timeout because **nothing told it to stop**. The payment worker *could* have been made idempotent, but it wasn't — which means:

1. **Every other consumer** of this queue may have the same problem (email sends, webhook deliveries, ledger entries, Stripe webhook handler)
2. The fix belongs at two levels: **database constraint** (Control) + **queue idempotency keys** (Control)

## **Proposed devices**

| Device | Rung | How |
|---|---|---|
| **Unique DB constraint** | Control | Add `UNIQUE(order_id, stripe_idempotency_key)` to charges table. No code change needed; DB refuses duplicates. |
| **Require idempotency keys at Stripe** | Control | Pass `idempotency_key=<order_id>` to *every* Stripe call (not optional). Stripe will return the same charge ID if retried. |
| **Queue message deduplication** | Control | Most queues support this natively (SQS: use message deduplication ID = order_id). Messages replayed within dedup window return same result. |
| **Sweep other consumers** | Control | Audit every consumer on this queue for the same pattern. Apply idempotency keys or message deduplication. |
| **Regression test** | Detection | Inject a timeout + redelivery; assert charge count = 1. Proves the fix works. |

**Why Control matters here**: You have proof this class of mistake happens. The cost of going higher is near-zero — constraints and Stripe's native idempotency are built-in, not new infrastructure.

## **Class sweep questions**

Before you close this:

1. **Which queue is the payment worker listening on?** (That queue likely delivers to other services too — emails, webhooks, ledger, Stripe webhook handler)
2. **Are all queue consumers idempotent?** (Likely not; audit each one)
3. **Where else do you call Stripe?** (Refunds, updates, subscriptions — do they all pass idempotency keys?)
4. **Do you have a regression test** that forces a timeout + redelivery and shows the charge only happens once?

Before moving on, **run the retro test**: force a Stripe timeout in staging, watch the retry fire, confirm charge count = 1. If it's still 2, the device hasn't worked.

What's your stack for the queue and payment service?