No — and the check you added is itself a new hazard. Your payment worker isn't in this repo (only `benchmarks/fixtures/payments.ts`), so this is from your description.

## The three things

- **Defect:** 340 customers charged twice.
- **Mistake:** the retry path called `charge()` again with no idempotency key.
- **Hazard:** your queue is at-least-once, `charge()` is callable without an idempotency key, and nothing outside the worker process refuses a second charge.

Only the third one is fixable. The first two are already over.

## Why the dup-check doesn't close it

**It loses the race that caused this incident.** Attempt 1 timed out — meaning it had *no response from Stripe and therefore wrote no row*. Attempt 2 does its `SELECT`, sees nothing, and charges. The check is a read followed by a write with a gap in between; your incident lives in that gap. It would not have prevented last night.

**"Recent + same amount" is a guess, not an identity.** A customer legitimately buying the same $9.99 item twice now silently loses a charge. You've traded a visible double-charge for an invisible dropped one — harder to detect, harder to refund.

**It's in the worker.** Rung 2 at best. Every other consumer on that queue still has the hazard.

★ Insight ─────────────────────────────────────
A timeout is not a failure — it's an *unknown*. The whole bug is code that treats "no response" as "didn't happen." Idempotency keys work because they move the decision to a party that *does* know: Stripe already has the record your worker never received.
─────────────────────────────────────────────────

## The Control-rung device

1. **Stripe `Idempotency-Key`, derived from a stable business ID** — the order/invoice ID, never a per-attempt UUID. Stripe then refuses attempt 2 itself. The constraint survives your process crashing mid-flight, which no in-process check can.
2. **Unique DB constraint** on that key in your charges table. Insert the intent row *before* calling Stripe. Two concurrent workers, one succeeds, the other gets a constraint violation instead of a charge.
3. **Make the key a required parameter** of your charge wrapper — no default, no `Optional`. If it can be omitted, it will be.

Layers 1 and 2 are independent on purpose; either alone would have stopped this.

## The part that matters most: it's the second time

That's the real finding. The hazard isn't payments — it's that consumers on an at-least-once queue are written as if delivery were exactly-once. Every handler on that queue is suspect: confirmation emails, outbound webhooks, ledger writes, credit grants. Sweep by shape, not by the word "charge": any consumer that performs a side effect without a key the broker can't influence.

What was the first incident? If it was also a redelivery, that confirms the class and changes what this fix is worth.

---

**One decision I can't make for you:** what is the stable identity of a charge in your domain? Options — the order ID (one charge per order, ever), the invoice line ID (allows deliberate re-bills), or `(subscription_id, billing_period)` for recurring. This choice determines what a *legitimate* second charge looks like, and getting it wrong means either blocking real payments or leaving the door open.

Tell me which, and where the payments repo lives, and I'll write the retro doc, the constraint migration, and a test that reproduces the redelivery race and shows it refused.