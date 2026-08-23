This is the poka-yoke plugin repo, not your payments service — so I can analyse the design but can't run the class sweep against your code. Flagging that up front; it's the step that matters most here.

## Short answer: no

The new check is a **check-then-act race** — the same shape that produced the incident, with an extra query in front of it.

**Defect** — 340 customers charged twice.
**Mistake** — the retry path called Stripe's charge without an idempotency key.
**Hazard** — the charge call *succeeds without one*. Nothing in the signature, the type, or the database requires a charge to be idempotent.

Your fix addresses the mistake. The hazard is untouched.

## Why the recent-charge check doesn't close it

1. **It races on exactly the failure you had.** The worker timed out at 30s — that doesn't mean Stripe finished. Redelivery starts worker B while worker A is *still blocked*. B's `SELECT` for a recent charge runs against a row A hasn't written yet. Both see nothing, both charge. Concurrency is the trigger, and the check runs outside the concurrency boundary.
2. **It asks the party that can't answer.** After a timeout, your DB doesn't know whether the charge happened. Stripe does.
3. **It's ambiguous by construction.** "Recent, same amount" has no correct window. Too short misses duplicates; too long silently refuses a customer legitimately buying the same $49 item twice — and that failure is *quiet*, nobody gets paged for a declined-by-your-own-heuristic sale.

Rung: **Detection**, and only on the sequential path. Control is available and cheap here.

## The device

| Device | Rung | Covers |
|---|---|---|
| Idempotency key as a **required** param, derived from the queue message ID | Control | every caller |
| `UNIQUE` on `(idempotency_key)` in your charges table | Control | scripts, other services, psql |
| Key reserved in the **same transaction** as the write, bound to the payload | Control | partial-failure replay |
| Stripe↔orders reconciliation job | Detection | what turns 340 into 3 |

The critical detail: Stripe returns the *original response* for a repeated key. The retry **learns the outcome** instead of guessing. A key generated fresh per attempt (`uuid4()` at call time) is the bug wearing a costume — it must be deterministic from the message identity.

Second finding, separately: **nothing caught this.** No reconciliation between Stripe's charge list and your orders. That gap is its own hazard.

`★ Insight ─────────────────────────────────────`
- A unique constraint that *rejects* the duplicate is necessary but not sufficient — a caller that retries and gets a constraint violation still doesn't know if attempt one succeeded. Idempotency means replaying the stored result, not refusing the second call.
- "Second time" is the signal to sweep, not to patch. Every other effect reachable from that queue — refunds, payouts, subscription creation, outbound webhooks, inventory decrements — has the same hazard until proven otherwise. At-least-once delivery isn't the bug; non-idempotent effects are.
`─────────────────────────────────────────────────`

## What I need from you

**The key derivation is the one real design decision**, and it's yours — I don't know your queue semantics.

If the message ID is stable across redeliveries (SQS `MessageId`, not `ReceiptHandle`), scope the key to it. If your queue mints a new ID per redelivery, you need a business-level key — `(order_id, attempt_intent)` — and then you must decide what happens when a customer *legitimately* pays the same order twice.

Which is it for your queue? Once I know, I'll write the retro doc and the required-parameter change.

Point me at the payments repo and I'll run `detect_hazards.py --id M2` across it for the class sweep.