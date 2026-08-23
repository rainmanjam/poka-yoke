Using **poka-yoke → `retro`** (something already broke, second occurrence). I don't have your payment worker in this repo, so this is the analysis; the sweep needs you to point me at the code.

## Short answer: no, and specifically it would not have prevented last night.

## The three things, separated

- **Defect** — 340 customers charged twice, refunded.
- **Mistake** — the redelivered message ran the charge path a second time.
- **Hazard** — *a charge is an effect with no identity.* Nothing in the system ties "this charge attempt" to "this business event," so a second attempt is indistinguishable from a legitimate second purchase — to your code and to Stripe.

## Why the new check doesn't close it

**It's a check-then-act race (M5), and the race window is exactly your incident.** The first worker was blocked waiting on Stripe. At that moment there is no recorded charge — that's *why* it timed out. The redelivered message looks for "a recent charge with the same amount," finds nothing, and charges. Your fix reads local state that is, by construction, not yet written during the only window that matters.

Three more edges:
- **Wrong key.** Amount + recency is a heuristic. A customer legitimately buying the same thing twice gets silently under-charged — a defect in the opposite direction, and a quiet one.
- **"Recent" is a guess.** A redelivery outside the window double-charges anyway.
- **A timeout is not a failure.** The worker treated "no answer" as "didn't happen." It's *unknown*, and the only safe resolution is asking Stripe with the same identity.

Rung: the check is **Detection at best** (rung 3) — and racy, so unreliable even there. You need **Control**.

`★ Insight ─────────────────────────────────────`
The give-away that a fix is rung 3 wearing a rung 1 costume: it *reads* state to decide whether an effect already happened. Control doesn't read — it *writes first* and lets a constraint refuse the second writer.
`─────────────────────────────────────────────────`

## The device (Control)

1. **Derive the key from the business event, never per attempt.** `order:<id>:capture`, not a UUID minted in the worker — a redelivery mints a new UUID and you're back where you started. This is the single most common way idempotency keys get installed and still fail.
2. **Reserve before you call.** `INSERT INTO payment_attempts (key, payload_hash) ... ON CONFLICT DO NOTHING`. Lose the insert → you're the duplicate; don't call Stripe. Unique constraint in the schema (F6), not in the app.
3. **Pass it to Stripe too.** `Idempotency-Key` header. Now even a lost reservation can't produce a second charge — belt and braces at two layers, and it turns your timeout retry into "Stripe replays the original charge."
4. **Replay the stored result.** Per the catalog's M2 note: rejecting a duplicate is *not* idempotence. The second caller must receive the first attempt's outcome, or your queue just retries forever.
5. **Bind the key to the payload.** Same key, different amount → hard error, never a silent no-op.
6. **Make the raw client unreachable.** The key must be a *required* argument on the only wrapper allowed to touch Stripe, with an ESLint `no-restricted-imports` on the SDK outside that module. An optional idempotency key is rung zero.

## Why it's the second time — the finding that actually matters

Your queue is at-least-once, and **nothing in the consumer contract says handlers must be idempotent.** The payment worker isn't special; it's just the consumer where the bug costs money and gets noticed. Before fixing the worker, sweep: every consumer on that queue, outbound emails and webhooks, ledger/balance read-modify-writes, subscription and provisioning handlers, refunds and payouts.

The platform-level Control is a dispatcher that wraps *every* handler in reserve-and-replay, with the dedupe ID required in the message envelope — so a new consumer is idempotent by default rather than by remembering. That's what stops a third incident.

## Verify it, don't assume it

Reproduce the original: block the worker mid-Stripe-call, redeliver, assert exactly one charge in Stripe test mode. Then remove the constraint and watch the test go red. A device nobody has seen fire is a rumour.

---

**One decision I can't make for you** — it shapes everything above: the **key scope**. `order_id` alone means a customer can never be charged twice for one order, ever (safest, but blocks legitimate re-captures). `order_id + line_item_version` allows intentional re-charges. And separately: when the same key arrives with a *different* amount, is that a hard 409, or do you take the first? Tell me your call on those two and I'll write the retro doc plus the wrapper against your actual code — point me at the repo and I'll run the class sweep with `detect_hazards.py --id M2` first, so we know the real number of exposed sites before you decide how much this is worth.