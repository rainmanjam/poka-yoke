Using the `retro` mode. Short answer: **no, it's not enough** — the check you added is hazard M5 (check-then-act race) layered on top of hazard M2 (non-idempotent retryable effect). It narrows the window; it doesn't close it.

## Retro — duplicate charge on queue redelivery

**Defect**: 340 customers charged twice, refunded.
**Mistake**: the redelivered message re-ran `charge()` for work whose first attempt had actually succeeded at Stripe.
**Hazard**: `charge()` can be called without an idempotency key, and nothing in your system records "a charge for *this intent* is in flight/done" atomically with the attempt.

### Why the new check is rung 3 wearing a rung-1 costume

"Look for a recent charge with the same amount" fails in exactly the scenario that caused the incident:

1. **The timeout is the race.** Attempt 1 timed out — so from your side there *is no recorded charge* to find. Stripe has it; your DB doesn't. Attempt 2 looks, sees nothing, charges again. The check misses the original case unless you also reconcile against Stripe first.
2. **Two workers, one message.** Redelivery commonly runs concurrently with the still-running first attempt. Both check, both see nothing, both charge. Check-then-act without a lock.
3. **Same amount ≠ same intent.** Two legitimate $20 orders in the window get the second one silently dropped — a false positive that *loses revenue* and is harder to notice than a double charge.
4. **"Recent" is a magic window** (C5). Redelivery after a 10-minute visibility timeout vs a 5-minute window — which did you pick, and why?

### Devices

| Device | Rung | Notes |
|---|---|---|
| **Stripe idempotency key = your payment-intent ID**, passed on every `charge()` call | Control | Stripe dedupes server-side for 24h and replays the original result to the retry. This alone would have made the incident a no-op. |
| Make the key a **required** parameter of your `charge()` wrapper (type/signature, not convention) | Control | An optional key is rung 0. This is the class fix. |
| `payment_attempts` row with **unique `(order_id)`**, inserted in the same transaction *before* calling Stripe, status `pending → succeeded/failed` | Control | Second worker hits the unique violation → it *reconciles* (look up by key at Stripe) rather than charges. This closes the concurrent-worker race the Stripe key alone leaves (key collision at Stripe returns the result, but only if both requests carry it). |
| On timeout: **reconcile, don't retry** — retrieve the PaymentIntent by idempotency key/metadata before deciding | Control | Timeout means *unknown*, not *failed*. Treating unknown as failed is the root mistake. |
| Regression test: inject a timeout on attempt 1 + redeliver → assert exactly one Stripe call | Detection | Prove the device fires: remove the key, watch it go red. |
| Daily reconciliation: Stripe charges vs your ledger, alert on >1 per intent | Detection | The "second time" tells you the class exists elsewhere; this finds the ones you haven't thought of. |

### Class sweep (you need to run this, I don't have the repo)

Search by shape, not by text: every external mutation reachable from a queue consumer, cron, or retry loop — refunds, payouts, subscription creation, invoice finalize, **emails/SMS**, webhook fan-out. Run `plugins/poka-yoke/scripts/detect_hazards.py --paths <repo> --id M2` and `--id M5`. I'd expect the refund path you just used to have the same shape.

### Why nothing caught it (the escape)

No test simulates at-least-once delivery. Add one test harness that redelivers *every* message type once; it'll surface the sweep for you.

**Accepted risk after all the above**: none for double charges on this path. Remaining: Stripe key expiry at 24h — a redelivery older than that is a bug in your queue config, not a payments problem.

Want me to write this up as `docs/poka-yoke/retro-2026-08-21-double-charge.md` and draft the `charge()` signature + attempts table for your language?