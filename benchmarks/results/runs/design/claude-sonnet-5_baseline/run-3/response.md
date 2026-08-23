**Misuse enumeration first** — a `Subscription` interface with all fields optional (`trialEndsAt?`, `retryCount?`, `cancelReason?`, `renewalDate?`) would let you construct `{status: "active", cancelReason: "..."}`  and every reader would have to remember which fields are valid for which status. That's the hazard to close.

```typescript
// --- Branded IDs: a SubscriptionId and CustomerId are both strings underneath,
// but they mean different things and should never be swappable at a call site.
type Brand<T, B extends string> = T & { readonly __brand: B };
type SubscriptionId = Brand<string, "SubscriptionId">;
type CustomerId = Brand<string, "CustomerId">;

// --- Cancellation reasons: "voluntary: boolean" + "reason: string" is itself a
// mini bag-of-optionals — it lets `{ voluntary: true, reason: "payment_failed" }`
// type-check even though that reason only makes sense when voluntary is false.
// Nesting the union closes that gap instead of just commenting "don't do that."
type VoluntaryReason = "too_expensive" | "missing_features" | "switched_competitor" | "no_longer_needed" | "other";
type InvoluntaryReason = "payment_failed" | "fraud_flagged" | "chargeback" | "compliance_hold";

type Cancellation =
  | { voluntary: true; reason: VoluntaryReason; feedback?: string }
  | { voluntary: false; reason: InvoluntaryReason };

interface SubscriptionBase {
  id: SubscriptionId;
  customerId: CustomerId;
}

interface TrialingSubscription extends SubscriptionBase {
  status: "trialing";
  trialEndsAt: Date;
}

interface ActiveSubscription extends SubscriptionBase {
  status: "active";
  renewalDate: Date;
}

interface PastDueSubscription extends SubscriptionBase {
  status: "past_due";
  retryCount: number;        // invariant: >= 0 — enforce in the constructor below
  gracePeriodEndsAt: Date;
}

interface CanceledSubscription extends SubscriptionBase {
  status: "canceled";
  canceledAt: Date;
  cancellation: Cancellation;
}

type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;
```

Two devices worth calling out on top of the union itself:

```typescript
// Exhaustiveness: adding a fifth status ("paused"?) next year breaks every
// switch that doesn't handle it, at compile time, not in prod three weeks later.
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

function hasAccess(sub: Subscription): boolean {
  switch (sub.status) {
    case "trialing":  return sub.trialEndsAt > new Date();
    case "active":    return true;
    case "past_due":  return sub.gracePeriodEndsAt > new Date();
    case "canceled":  return false;
    default:          return assertNever(sub);
  }
}

// Illegal transitions: cancelSubscription only accepts the three non-canceled
// variants, so "cancel an already-canceled subscription" is a type error, not
// a runtime check you have to remember to write.
type CancelableSubscription = TrialingSubscription | ActiveSubscription | PastDueSubscription;

function cancelSubscription(
  sub: CancelableSubscription,
  cancellation: Cancellation,
  canceledAt: Date,
): CanceledSubscription {
  return { id: sub.id, customerId: sub.customerId, status: "canceled", canceledAt, cancellation };
}
```

`★ Insight ─────────────────────────────────────`
1. This is the "bag of optionals vs. sum type" hazard from the design ritual — an interface with N optional fields legally admits 2^N states, most of which are garbage. The discriminated union on `status` admits exactly 4.
2. `cancelSubscription`'s parameter type is doing typestate work without a full typestate machine: excluding `CanceledSubscription` from the input type is cheaper than a runtime `if (sub.status === "canceled") throw`, and it can't be forgotten.
3. TypeScript's structural typing is the honest limit here — nothing stops someone from hand-building a `PastDueSubscription` object literal with `retryCount: -1`, bypassing any constructor you write. Closing that fully needs private constructors/nominal branding, which is usually not worth the ceremony unless this type crosses a lot of hands.
`─────────────────────────────────────────────────`

One thing I deliberately left open, and it's the one only you can close: **which transitions are legal**. Can `past_due` go back to `active` directly, or must it pass through a payment-confirmation step? Can `trialing` skip straight to `canceled` with a refund? That's your billing policy, not a type-design question — I'd rather you encode it than guess. Want to sketch the transition matrix as a small `canTransition(from, to): boolean` (or a lookup table), and I'll wire it into `cancelSubscription`'s sibling functions?