Using **poka-yoke:retro**. This repo is the plugin itself, not your payment service — so I can't run the class sweep on your actual code. Answering the judgment question first.

## No. The check cannot fire in the incident it was written for.

**Defect**: 340 customers charged twice.
**Mistake**: retry called `charge()` again with no idempotency key.
**Hazard**: the payment path is not idempotent *as a property* — it depends on a runtime lookup being correct and timely. Nothing structurally prevents two charges.

Walk your fix through the actual timeline:

1. Worker calls Stripe. Stripe **succeeds**. Your client times out waiting on the response.
2. Because it timed out, your code never wrote the charge row.
3. Queue redelivers. Attempt 2 queries "recent charge, same amount" — **and finds nothing**, because attempt 1's row was never written.
4. Charges again.

The check reads a table that is empty by construction in exactly the failing case. It's rung 3 (Detection) wearing a rung 1 costume. Three more holes:

- **TOCTOU.** Redelivery is often concurrent with attempt 1 still in flight. Both read "no charge," both proceed. A check without a unique constraint behind it is a race.
- **Amount is not identity.** A customer legitimately buying twice gets silently *under*-charged. That defect generates no support tickets — you'd never learn it's happening.
- **"Recent" is a magic window.** DLQ replay or a worker restart hours later sails past it.

## What actually closes it

| Device | Rung | Why |
|---|---|---|
| Idempotency key on every Stripe call, derived deterministically from the message/order ID — never random per attempt | **Control** | Stripe dedupes server-side. Attempt 2 gets attempt 1's result back, including when attempt 1 "timed out." |
| Key is a **required** param; `charge()` uncallable without one | **Control** | Removes the affordance, not the instance |
| DB unique constraint on `(order_id, purpose)` | **Control** | Survives key expiry and code paths you didn't think of |
| Write the attempt row **before** calling Stripe | Control | Makes any lookup meaningful; enables recovery-on-timeout |
| Timeout handled as *unknown*, never as *failed* | Control | This is the root belief that produced both incidents |
| Reconciliation job: Stripe charges vs. your ledger, alert on >1/order | Detection | Catches what the above misses |

**The "second time" is the real finding.** The hazard isn't in the worker — it's that your queue is at-least-once and side-effecting consumers aren't idempotent. Every other consumer of that queue has this bug latent: refunds, transfers, provisioning, emails, webhook fanout. That sweep is worth more than the payment fix.

★ Insight ─────────────────────────────────────
A timeout is the one failure that is genuinely *ambiguous* — it tells you nothing about whether the remote side committed. Code that maps timeout→retry is asserting "it didn't happen," which is unprovable. Idempotency keys work precisely because they make that assertion unnecessary.
─────────────────────────────────────────────────

One thing only you can decide: **what the idempotency key is scoped to.** `order_id` blocks a genuine repeat purchase of the same cart; `order_id + attempt_intent` allows it but needs the client to mint the intent. Which is right depends on whether repeat-buy-same-cart is real in your product.

Tell me and I'll write the retro doc plus the regression test that proves the device refuses a redelivery — point me at the service repo and I'll sweep the other consumers too.