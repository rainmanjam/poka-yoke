**Short answer: no.** The check you added is rung 3 (detection, done inside the worker) dressed as prevention — and it has its own double-charge window. Here's the retro, run the way the `retro` skill lays it out.

## Defect / mistake / hazard

- **Defect**: 340 customers charged twice; refunded.
- **Mistake**: the redelivered message called `charge()` a second time.
- **Hazard**: **`charge()` can be called without an idempotency key, and nothing — not the type, not Stripe, not your database — refuses it.** That hazard is still present after your fix. "Second time this has happened" is the evidence: the first fix also patched a path, not the property.

## Why the "recent charge with same amount" check is not enough

1. **Check-then-act race (catalog M5).** Timeout → redelivery → the original attempt is still in flight at Stripe, or succeeded but its result never reached your DB. The lookup sees no charge and charges again. This is *exactly* the scenario that bit you — the check looks for a record the timed-out attempt never wrote.
2. **False positives.** A legitimate second order for the same amount within the window is silently skipped. You've traded duplicate charges for lost revenue, and that failure is quiet.
3. **It's per-call-site.** Any other path that reaches `charge()` — admin retry button, backfill script, subscription renewer, a second worker — is unprotected.
4. **It's an optional convention.** The next engineer who writes a worker has to *remember* the heuristic. Rung zero.

## The devices, by rung

| Device | Rung | What it covers |
|---|---|---|
| **Required idempotency key on `charge()`** — no default; derive from the message/order ID, not a random UUID at retry time. Pass as Stripe's `Idempotency-Key`; Stripe replays the original result for 24h. | **Control** | every caller, including future ones |
| **`payment_attempts(order_id, key) UNIQUE`**, key reserved in the **same transaction** as the charge record, *before* calling Stripe; bind it to the payload (amount, currency) so a reused key with a different amount errors instead of no-op'ing | **Control** | the in-flight/timeout window Stripe's key doesn't cover once your DB and Stripe disagree |
| Worker consults its own attempt row first: if a key exists with status `pending`, **re-query Stripe** by that key rather than re-charge | Control | the timeout case specifically |
| Regression test: simulate timeout + redelivery, assert exactly one Stripe call | Detection | proves the device fires |
| Reconciliation job: Stripe charges vs. local attempts, alert on > 1 per order | Detection | catches what you haven't thought of |

Control would mean making the parameter required, which breaks every existing caller — that's the point. The compile error *is* the sweep.

## Class sweep (do before closing)

Grep for every external mutation reachable from a retry, queue consumer, or cron: refunds, emails, webhooks, payouts, invoice creation. Each one without a required key is the same hazard. The plugin's detector can find them mechanically:

```
python3 plugins/poka-yoke/scripts/detect_hazards.py --paths <your-repo> --id M2
```

Report the count — "same hazard at N other sites" is what justifies the breaking change.

## Verify before you close

Break it on purpose: replay a message with the same key and watch the unique constraint / Stripe replay refuse the second charge. Then change the amount under the same key and confirm it *errors* rather than silently returning the old charge. If you've never seen the device go red, it's a belief, not a control.

## Accepted risk

Stripe's key expires after 24h; a redelivery past that relies on your local unique constraint alone. That's fine — say it in the write-up.

**What's next**: the `retro` skill wants this written to `docs/poka-yoke/retro-2026-08-21-double-charge.md` in *your* payment repo with `poka-yoke:` marker comments at each device. I didn't write it here because this repo is the plugin, not your service — point me at the payment worker code and I'll run the sweep and draft the constraint + test.