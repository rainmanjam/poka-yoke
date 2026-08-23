Using **poka-yoke:design** — you're defining a new data model, so the mistake-proofing *is* the code.

## First, the misuse enumeration

Before the signature, what goes wrong with the obvious shape (`{ status, trialEndsAt?, renewsAt?, retryCount?, gracePeriodEndsAt?, cancelReason?, voluntary? }`):

1. **6 optional fields claim 2^6 = 64 states. You have 4.** `{status: "active", cancelReason: "too_expensive"}` typechecks.
2. **`voluntary: boolean` + `cancelReason: string` are independently settable.** `voluntary: true, reason: "payment_failed"` is expressible — and it will silently corrupt your churn numbers, because voluntary and involuntary churn have *disjoint* reason sets and different retention plays.
3. **`retryCount: number` is unbounded.** Nothing stops dunning running forever.
4. **Every consumer re-derives "does this person have access?"** as `status === 'active'`, which silently locks out `past_due` customers inside their grace period. That's the bug that generates support tickets.
5. **Adding `paused` next year breaks nothing** — every `if/else` chain silently falls through.
6. **Your list has no state for "canceled but paid through the end of the period."** That's not an edge case; it's the majority of voluntary cancellations.

---

## The types

```ts
// ─── Identity: contact lens (C1/C3) ────────────────────────────────
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId     = Brand<string, "CustomerId">;
export type PriceId        = Brand<string, "PriceId">;
// chargeCustomer(subId, custId) no longer compiles with the args swapped.

// Bounded, so dunning cannot loop forever (F7).
export const MAX_PAYMENT_RETRIES = 4;
export type RetryCount = Brand<number, "RetryCount">;
export const RetryCount = (n: number): RetryCount => {
  if (!Number.isInteger(n) || n < 0 || n > MAX_PAYMENT_RETRIES)
    throw new RangeError(`retryCount ${n} outside 0..${MAX_PAYMENT_RETRIES}`);
  return n as RetryCount;
};

/** Time is a parameter, never an ambient read (C9). */
export interface Clock { now(): Date }

// ─── The state union ───────────────────────────────────────────────
export type Subscription = {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
  readonly priceId: PriceId;
} & SubscriptionState;

export type SubscriptionState = Trialing | Active | Canceling | PastDue | Canceled;

interface Trialing {
  readonly status: "trialing";
  readonly trialEndsAt: Date;
  /** null ⇒ no payment method on file: this trial lapses, it does not convert. */
  readonly convertsToPriceId: PriceId | null;
}

interface Active {
  readonly status: "active";
  readonly renewsAt: Date;
}

/** The state your list was missing: cancelled, but paid through the period. */
interface Canceling {
  readonly status: "canceling";
  readonly canceledAt: Date;
  readonly accessEndsAt: Date;   // == the renewsAt they already paid for
  readonly reason: VoluntaryReason;
  readonly feedback: string | null;
}

interface PastDue {
  readonly status: "past_due";
  readonly retryCount: RetryCount;
  readonly gracePeriodEndsAt: Date;
  readonly enteredPastDueAt: Date;
}

interface Canceled {
  readonly status: "canceled";
  readonly canceledAt: Date;
  readonly accessEndsAt: Date;
  readonly cancellation: Cancellation;   // ← replaces voluntary + reason
}

// ─── The key move: nested union instead of boolean + string (C2/C4) ─
export type Cancellation =
  | { readonly kind: "voluntary";
      readonly reason: VoluntaryReason;
      readonly feedback: string | null }
  | { readonly kind: "involuntary";
      readonly reason: InvoluntaryReason;
      readonly finalRetryCount: RetryCount };

export type VoluntaryReason =
  | "too_expensive" | "missing_features" | "switched_to_competitor"
  | "no_longer_needed" | "temporary_pause" | "other";

export type InvoluntaryReason =
  | "payment_retries_exhausted" | "chargeback" | "fraud_suspected" | "compliance_hold";
```

`★ Insight ─────────────────────────────────────`
- `voluntary: boolean` + `reason: string` is 2 × N combinations, most of which are nonsense. The nested union is exactly `|Voluntary| + |Involuntary|` — and it makes `finalRetryCount` *required* on involuntary cancels, so your dunning post-mortems always have the data.
- Notice `feedback` only exists on the voluntary branch. Asking a customer why they left when their card was declined is a bug the type now prevents.
`─────────────────────────────────────────────────`

## Derive access once, exhaustively

```ts
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription state: ${JSON.stringify(x)}`);
}

export type Entitlement =
  | { readonly access: "full" }
  | { readonly access: "full"; readonly warn: "payment_failing"; readonly until: Date }
  | { readonly access: "none"; readonly since: Date };

export function entitlement(sub: Subscription, clock: Clock): Entitlement {
  const now = clock.now();
  switch (sub.status) {
    case "trialing":
      return now < sub.trialEndsAt ? { access: "full" } : { access: "none", since: sub.trialEndsAt };
    case "active":
      return { access: "full" };
    case "canceling":
      return now < sub.accessEndsAt ? { access: "full" } : { access: "none", since: sub.accessEndsAt };
    case "past_due":
      return now < sub.gracePeriodEndsAt
        ? { access: "full", warn: "payment_failing", until: sub.gracePeriodEndsAt }
        : { access: "none", since: sub.gracePeriodEndsAt };
    case "canceled":
      return now < sub.accessEndsAt ? { access: "full" } : { access: "none", since: sub.accessEndsAt };
    default:
      return assertNever(sub);
  }
}
```

Add `paused` next year and **the build breaks here** — which is the correct behaviour. Turn on `@typescript-eslint/switch-exhaustiveness-check` so it breaks at every other switch too.

## Transitions: one door in (M3)

Every field above is `readonly`, and no constructor is exported. The only ways to obtain a `Subscription` are `parseSubscription` (at the DB/webhook boundary) and `transition`. Nobody can write `sub.status = "active"` from a handler.

```ts
export type SubscriptionEvent =
  | { readonly type: "trial_converted";     readonly renewsAt: Date }
  | { readonly type: "trial_expired" }
  | { readonly type: "payment_succeeded";   readonly renewsAt: Date }
  | { readonly type: "payment_failed";      readonly gracePeriodEndsAt: Date }
  | { readonly type: "retries_exhausted" }
  | { readonly type: "customer_canceled";   readonly reason: VoluntaryReason;
                                            readonly feedback: string | null }
  | { readonly type: "chargeback_received" };

export type TransitionError =
  { readonly kind: "illegal"; readonly from: SubscriptionState["status"];
    readonly event: SubscriptionEvent["type"] };

export function transition(
  sub: Subscription,
  event: SubscriptionEvent,
  clock: Clock,
): Result<Subscription, TransitionError> { /* … */ }
```

**Honest rung statement:** this is Control against *assignment from anywhere* (there is no other way to change state), but only Warning against an illegal event — because events arrive from Stripe webhooks at runtime, compile-time typestate cannot gate them. Compile-time typestate would work only if every transition originated in your own code, which it doesn't.

## Push the invariants into the database (F6)

Types vanish at compile time; a migration script or a Rails service in two years will not see them.

```sql
ALTER TABLE subscriptions ADD CONSTRAINT variant_fields_match_status CHECK (
  CASE status
    WHEN 'trialing'  THEN trial_ends_at IS NOT NULL AND renews_at IS NULL AND cancel_kind IS NULL
    WHEN 'active'    THEN renews_at IS NOT NULL AND cancel_kind IS NULL AND retry_count IS NULL
    WHEN 'canceling' THEN access_ends_at IS NOT NULL AND cancel_reason IS NOT NULL
    WHEN 'past_due'  THEN retry_count BETWEEN 0 AND 4 AND grace_period_ends_at IS NOT NULL
    WHEN 'canceled'  THEN cancel_kind IS NOT NULL AND canceled_at IS NOT NULL
  END
);

-- Voluntary and involuntary reasons cannot cross over.
ALTER TABLE subscriptions ADD CONSTRAINT cancel_reason_matches_kind CHECK (
  cancel_kind IS NULL
  OR (cancel_kind = 'voluntary'   AND cancel_reason IN ('too_expensive','missing_features','switched_to_competitor','no_longer_needed','temporary_pause','other'))
  OR (cancel_kind = 'involuntary' AND cancel_reason IN ('payment_retries_exhausted','chargeback','fraud_suspected','compliance_hold'))
);

-- One live subscription per customer.
CREATE UNIQUE INDEX one_live_sub_per_customer ON subscriptions (customer_id)
  WHERE status IN ('trialing','active','canceling','past_due');

-- Webhook idempotency: at-least-once delivery is the norm (M2).
CREATE UNIQUE INDEX ON subscription_events (stripe_event_id);
```

A row-level `CHECK` cannot police *transitions* — it sees the new row, not where it came from. Policing `canceled → active` in the database needs a trigger or a transition table. The `transition()` function is the real device there.

## What I left possible, deliberately

- **Illegal transitions are rejected at runtime, not compile time** — webhook-driven, as explained above.
- **`Date` rather than a branded `Instant`.** JS `Date` is already an unambiguous instant; the real hazard is ambient `new Date()`, which the `Clock` parameter closes. A branded wrapper would add ceremony for no additional guarantee.
- **No `Money` type here** — you didn't mention amounts. If `renewsAt` ever gains a sibling `amount`, make it integer minor units with a currency, never a float.

---

## One decision that's yours, not mine

The transition table encodes real billing policy, and getting it wrong costs money in both directions. Three questions I can't answer for you:

1. **`past_due` → `active` on a successful retry:** does `renewsAt` reset from the original anniversary (customer keeps their billing date, you eat the gap) or from the payment date (billing date drifts forward each failure)?
2. **A trial ending with a declined card:** `trialing → past_due` (you dun them) or `trialing → canceled` with `involuntary` (you don't)?
3. **`canceled` → reactivation:** same `SubscriptionId` resurrected, or a brand-new row? This determines whether your churn cohort math double-counts.

Fill in `transition()` — roughly 10 lines of `case` arms in the `past_due` and `trialing` branches — and the rest of the model follows from it. If you tell me your answers I'll write it out, or point me at the repo your SaaS actually lives in and I'll put these types in a file there rather than in this one.