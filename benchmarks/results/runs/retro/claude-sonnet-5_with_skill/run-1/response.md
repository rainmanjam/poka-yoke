No, that check isn't enough — and worse, it's likely to fail on the exact scenario that caused this incident.

**The three things, kept separate:**
- **Defect**: 340 customers double-charged.
- **Mistake**: the redelivered message triggered a second `charge()` call.
- **Hazard**: charging Stripe has no idempotency guarantee — nothing about the call ties it to "this logical charge, at most once."

**Why the "check for a recent charge" fix doesn't close that hazard:**

1. **It's check-then-act, not atomic.** Two deliveries of the same message (or a retry racing the original) can both run the lookup before either charge is recorded. Nothing serializes the check against the write.
2. **It fails specifically on a Stripe timeout — the trigger you just had.** A timeout means your worker never got a response, so on the *first* attempt it never got as far as recording a charge locally. When the redelivered message runs the "check for a recent charge" query, there's nothing there to find. This isn't an edge case of the fix — it's the exact shape of the incident it's meant to prevent.
3. **"Same amount" is a weak match key** — it'll produce both false negatives (miss it) and false positives (block a customer who legitimately buys the same $12.99 item twice in one session).

This is a rung-2-at-best "warning" device, and a leaky one. What you want is rung 1, **control**:

- **A stable idempotency key on the Stripe call**, derived from something that doesn't change across redeliveries — the order/invoice ID or the queue message's dedup ID, *not* a UUID generated fresh inside the worker (that's the classic mistake — a freshly-generated key defeats the whole mechanism on retry). Stripe will then refuse the second charge server-side.
- **A DB-level unique constraint** on something like `(order_id)` or `(order_id, status='succeeded')` for your charge records, so even if the Stripe call path has a bug, your own database physically cannot hold two successful charges for one order.

Keep a reconciliation job (Stripe charges vs. internal orders) as a rung-3 backstop, but that's detection after the fact, not prevention.

Since you said this is the second time: the real finding of a retro is rarely the one call site — it's every other place with the same shape. Do you have other queue consumers that call non-idempotent external APIs (other payment paths, email sends, inventory adjustments, webhook fan-out) without a stable idempotency key? That's worth a sweep before calling this closed, since "at-least-once delivery + non-idempotent handler" is a hazard that repeats by pattern, not by code path.

Want me to look at the actual worker code and propose the specific idempotency-key change, or do the sweep for other non-idempotent consumers first?