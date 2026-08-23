No — that fix stops the exact replay you just had, but it's a rung-3 (Detection) patch with a real gap, and this being the second occurrence is the signal to go to rung-1 (Control) instead of patching the symptom again.

**Separating the three things:**
- **Defect**: 340 customers double-charged, refunded after the fact.
- **Mistake**: the worker re-ran the Stripe charge after redelivery, without anything tying that second attempt back to the first.
- **Hazard**: charging is not idempotent by construction — nothing in the code or schema *requires* a stable key per logical charge, so a second attempt at the same logical payment is a request the system will happily fulfill.

**Why the "recent charge, same amount" check isn't enough:**

1. **It's a check-then-act race, and it's the exact race that caused the incident.** Queue redelivery after a timeout is often fast — sometimes near-simultaneous, sometimes across two worker instances. Both attempts can run the "any recent charge of this amount?" query before either has written its own charge row. The guard is bypassed by precisely the failure mode you're defending against.
2. **Amount is the wrong key.** It's not a stable identifier of *intent*. A customer legitimately buying two $50 items minutes apart gets silently blocked (false positive); meanwhile the check has no way to distinguish "this is a redelivery of charge X" from "this is an unrelated charge that happens to match" once volume or "recent" window gets fuzzy.
3. **It's reactive, not structural.** It's a runtime lookup that has to be remembered and correctly placed on every call path that can trigger a charge. It doesn't make the double charge *unrepresentable* — it makes it *usually caught*.

**The control-rung fix:** give every logical charge a stable idempotency key — generated once, at the point the charge intent is created (order ID, invoice ID, event ID — something that's identical across every redelivery of the same message, not regenerated per attempt) — and:

- Pass it as Stripe's `idempotency_key` on `charges.create`. Stripe's own idempotency layer will refuse a second charge for the same key even under concurrent requests — this closes the exact race your amount-check can't.
- Add a unique constraint on that key in your own payments table, so even a bug in the Stripe call path fails loudly at the DB layer instead of silently writing a second charge row.
- Make the key a **required** argument in the charge function's signature — not optional, not a boolean retry flag — so there's no call path that can reach Stripe without one.

**Escape question:** what should have caught this and didn't? If there was a first incident like this before, worth checking whether *that* fix was also a rung-3 patch (a check, a test, a monitor) rather than a rung-1 constraint — that pattern of "fix the symptom, not the affordance" is usually why it repeats.

**Class sweep:** I don't have your worker's repo open here, so I can't run the sweep myself — but the same hazard shape (at-least-once delivery + a side effect with no idempotency key) almost certainly exists anywhere else that queue feeds a consumer: receipt/notification emails, webhook handlers, ledger writes, subscription-status updates. Any of those re-firing on redelivery is the same defect wearing a different face. Worth grepping your worker codebase for every consumer of that queue and checking each one has an idempotency key, not just the payment path.

If you point me at the actual worker repo, I can run `detect_hazards.py` against it and do the sweep for real, plus draft the retro doc and the idempotency-key change itself.