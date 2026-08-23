No — the check you added narrows the failure window, it doesn't close it. Here's why, and what would.

**Defect**: 340 customers double-charged (refunded).
**Mistake**: the redelivered message called the charge path a second time.
**Hazard**: charging is not idempotent — nothing in your system guarantees two charge attempts for the same logical payment can't both succeed.

**Why the new check isn't the fix**: "look for a recent charge with the same amount before charging" is a check-then-act — the exact shape of bug you just had. Two things break it:

1. **TOCTOU race, same as before.** The scenario you described — worker times out waiting on Stripe, queue redelivers — often means the *first* charge already succeeded on Stripe's side, but your worker hadn't committed the charge record yet when the retry landed. The lookup finds nothing, charges again. Redelivery can also happen concurrently (two consumers), where both read "no recent charge" before either writes.
2. **"Same amount" is a weak key.** It produces false negatives (a customer legitimately charged the same amount twice in the window gets blocked) without giving you a real guarantee — it's not bound to a specific transaction.

This is a Detection-rung patch on a problem that needs a Control-rung fix.

**What would actually close it**:
- A stable idempotency key per logical charge — derived from the order/invoice ID, not freshly generated per attempt (a fresh UUID on retry defeats the whole point). Pass it as Stripe's `Idempotency-Key` header — Stripe then guarantees only one charge succeeds for that key even under concurrent retries, which is precisely your timeout→redelivery race.
- A unique constraint in your own DB on the order/invoice ID for the charges table, so even if application logic races, the second insert is rejected at the data layer, not inferred from a lookup.

Keep the "recent charge" check if you like, but as an alert/reconciliation signal, not the guard.

**The step worth not skipping**: you said this is the second time. That's a strong signal the hazard is bigger than the payment worker. Anything else consuming from that same queue and doing a non-idempotent side effect on redelivery — sending emails, firing webhooks, writing ledger entries — has the identical exposure. Worth a quick sweep of queue consumers before calling this closed.

Want me to write this up as `docs/poka-yoke/retro-2026-08-22-double-charge.md` per the retro skill format, and/or look at the actual worker code if it's in a repo I can see?