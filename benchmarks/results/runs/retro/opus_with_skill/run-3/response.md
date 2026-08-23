Using `poka-yoke:retro` — something already broke, and "second time" makes non-recurrence the actual ask. Your payment worker isn't in this repo (only `benchmarks/fixtures/payments.ts`), so I can analyse and propose but can't run the class sweep myself.

## Short answer: no, and it fails in the exact scenario that caused this

**Defect**: 340 customers double-charged, refunded.
**Mistake**: the redelivered message ran the charge path a second time.
**Hazard**: the charge effect is non-idempotent and reachable from an at-least-once queue — nothing in the type system or the database says "at most once per message." That's M2 in the hazard catalog.

Your dup-check has three independent holes:

1. **It's blind on the timeout path.** The worker timed out *waiting on Stripe* — meaning the first charge may have succeeded with the response lost. If the charge row is written after Stripe returns, there is no row. The check queries an empty table and says "proceed." The one failure mode it was written for is the one it can't see.
2. **It's a check-then-act race (M5).** Redelivery fires on visibility-timeout expiry, not on the first consumer dying. Both workers SELECT, both find nothing, both charge. The window is as wide as the Stripe call.
3. **"Same amount recently" is a heuristic, not an identity.** It silently refuses legitimate repeat purchases (two seats, a top-up, a retry after a real decline) — and nobody files a ticket for money they *weren't* charged. It also misses dupes when the amount is recomputed (proration, tax, FX), and "recent" expires before your DLQ does.

That lands at rung 2 that fails open. You need Control.

## The device

Reserve the key in your DB **in the same transaction, before Stripe is called**:

```sql
-- poka-yoke: rejects a second charge for the same message delivery [control]
CREATE UNIQUE INDEX ON payment_attempts (invoice_id, idempotency_key);
```

1. Mint the key at **enqueue** time, in the message body — stable across redeliveries, never a fresh UUID per attempt.
2. `INSERT ... ON CONFLICT DO NOTHING RETURNING *`. Lost the insert → do not charge; read the winner's row.
3. Only the winner calls Stripe, passing that key as `Idempotency-Key`. A replay then *returns the original charge* — the retry becomes a read, not a write.
4. Record the outcome; treat a reused key with a different amount as an error, not a no-op.

The DB constraint matters independently of Stripe's: Stripe's keys expire in 24h, DLQ replays don't.

Then make it un-forgettable — the charge client should have **no** call path that omits the key, and ideally should only accept a reservation record the reservation step produces. An optional idempotency key is rung zero in a costume.

`★ Insight ─────────────────────────────────────`
The ordering is the whole fix: reserve-then-effect turns an unknown outcome into a recorded one. Any device placed *after* the external call inherits that call's failure modes.
`─────────────────────────────────────────────────`

## The part that matters most: it's the second time

Two incidents of one shape means the hazard isn't in the payment worker — it's in pairing an at-least-once queue with consumers that mutate the outside world. Sweep, by shape not by text: every other consumer on that queue that emails/refunds/provisions/posts to a ledger; every Stripe webhook handler (Stripe redelivers those too); every retry wrapper, and what sits under it; every admin "re-run job" button. Then ask what incident #1's fix was — if it was also a per-call-site check, that's the pattern to break. The structural move is middleware that reserves the key before dispatching to any handler, so handlers can't opt out.

## One decision I shouldn't make for you

When the reservation conflicts and the existing row is still `in_flight`, there are three defensible policies: poll Stripe to resolve it, nack the message for later redelivery, or dead-letter for a human. That's a business call about whether a delayed charge or a stalled queue hurts you more.

Want me to write this up as `docs/poka-yoke/retro-2026-08-22-double-charge.md` and run `detect_hazards.py --id M2 M5 F6` across the service? Point me at the repo path and I'll do both, plus the regression test — the redelivery case that must be blocked *and* the near-miss two-legitimate-identical-charges case that must not be.