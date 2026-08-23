No — and the shape of the fix is why this is the second time.

**Separating the three things:**

- **Defect:** 340 customers charged twice.
- **Mistake:** the redelivered message called `charge()` a second time.
- **Hazard:** *the charge call is not idempotent, and the queue is at-least-once.* Those two facts are incompatible, and nothing in the system enforces the contract between them.

The check you added addresses the mistake on one path. It leaves the hazard fully intact.

## Why the check doesn't hold

1. **It's read-then-act with no lock.** Attempt 1 times out but is still in flight; the redelivery reads "no recent charge" and proceeds. Both attempts pass the check. Timeout retries are precisely the case where the two attempts overlap in time — the check is weakest exactly when it's needed.
2. **It queries the wrong source of truth.** The first attempt timed out, so your DB may have no charge row *even though Stripe charged the card*. The check consults the record that the failure mode corrupts.
3. **Amount is not identity.** Two legitimate identical charges get silently suppressed — you've traded double-charging for silent under-charging, which nobody will page you about.

## The Control-rung device

**Stripe idempotency keys, derived deterministically from business identity** — `invoice_id`, not a UUID minted per attempt. Stripe then collapses the retry server-side, in the system that actually knows what happened. Plus a **DB unique constraint on `(invoice_id, billing_period)`** so a duplicate row cannot exist even if the application logic is wrong again.

Timeout must stop meaning failure. It means *unknown* — resolve it by re-driving the same idempotency key, never by deciding.

## The part that matters more

Second occurrence means the hazard isn't in the payment handler — it's in **the worker framework**. Every consumer on an at-least-once queue with a non-idempotent side effect has this bug available right now: refunds, payouts, emails, provisioning, webhook fan-out.

The device that fits: the consumer refuses to dispatch a handler that hasn't declared an idempotency key derivation. Not a convention — a registration-time failure. Then the class is closed, not this instance.

Worth counting how many consumers currently have side effects and no key — that number is the real scope of the incident.

`★ Insight ─────────────────────────────────────`
• "Check before acting" is Detection rung (catches after the mistake, on the path you thought of); "the operation cannot be expressed twice" is Control rung. Retries are where that gap always shows.
• A timeout is the one error that carries no information about the outcome — treating it as failure is what turns one bug into two.
`─────────────────────────────────────────────────`

**One decision I shouldn't make for you:** what makes two charge attempts *the same charge*. `invoice_id` alone? `(subscription_id, billing_period)`? Retry-with-new-card must produce a *new* key, or a legitimate second attempt gets swallowed. That boundary is your billing policy, not a technical default.

Tell me your scope key and I'll write the retro doc and the constraint + framework guard against it. Where should the retro live — this repo, or your payments service?