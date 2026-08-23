**No, the current fix is not enough.** Your interim check is Detection/Warning at best—it catches the problem *after* redelivery but has a critical race condition. Let me walk through the full analysis:

## The three things

**Defect:** 340 customers double-charged; this is the *second* incident of this type.

**Mistake:** The Stripe payment worker timed out on first attempt, the queue redelivered, and the retry path called `charge()` again, which succeeded a second time.

**Hazard:** Charge operations do not require an idempotency key, and there is no database-level constraint preventing duplicate charges from the same transaction/order.

## Why the current fix is insufficient

Your "check for recent charge with same amount" is a **Warning-rung device** (catches at runtime) with a fatal TOCTOU race:

1. Thread A: check finds no recent charge → returns true
2. Thread B: redelivery arrives and also checks → returns true (it arrived between A's check and charge)
3. Both threads proceed to charge

It also has precision problems — multiple customers could legitimately have the same charge amount. This is **not a poka-yoke**; it's a speed bump.

## What needs to fix it (Control rung)

Make the mistake *impossible* at the database level:

1. **Idempotency key required** — not optional — on every charge operation. Schema this as a required parameter, not optional.
2. **Unique constraint** on `(order_id, idempotency_key)` or your equivalent. The database refuses the duplicate before any application logic runs.

This is motion-step checking (step 2 cannot succeed until step 1 is present).

## The broader hazard

Your git history notes: "identified queue-wide non-idempotent consumers (emails/webhooks/ledger/Stripe handler)." This is not just a Stripe problem—**this is a queue redelivery pattern that exists at every external operation in the system.** Before closing this retro, search for:

- Every Stripe call (emails to external systems, webhook deliveries, ledger writes)
- Every place where a timeout or transient failure could cause redelivery
- Whether idempotency keys are used uniformly

Do you have the design documented somewhere of what the idempotency key scope should be (order ID, customer ID, transaction ID)? That decision blocks implementation.