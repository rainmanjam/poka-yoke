**Misuses to rule out first:** a flat `{status, trialEndsAt?, retryCount?, gracePeriodEndsAt?, cancelReason?, voluntary?}` claims 2⁵ = 32 field combinations are legal when only 4 are. It lets you write an `active` sub with a cancel reason, or a `past_due` one with no grace period, and every reader has to null-check fields that "should" be there. The fix is a discriminated union — one variant per status, each carrying exactly its own fields.

```ts
// Shared by every state
interface SubscriptionBase {
  id: SubscriptionId;          // branded, not bare string
  customerId: CustomerId;
  planId: PlanId;
}

type SubscriptionId = string & { readonly __brand: "SubscriptionId" };
type CustomerId     = string & { readonly __brand: "CustomerId" };
type PlanId         = string & { readonly __brand: "PlanId" };

interface TrialingSubscription extends SubscriptionBase {
  status: "trialing";
  trialEndsAt: Date;
}

interface ActiveSubscription extends SubscriptionBase {
  status: "active";
  renewsAt: Date;
}

interface PastDueSubscription extends SubscriptionBase {
  status: "past_due";
  retryCount: number;
  gracePeriodEndsAt: Date;
}

type CancelReason =
  | { voluntary: true;  reason: "too_expensive" | "missing_features" | "switched_provider" | "other" }
  | { voluntary: false; reason: "payment_failed" | "fraud" | "tos_violation" };

interface CanceledSubscription extends SubscriptionBase {
  status: "canceled";
  canceledAt: Date;
  cancellation: CancelReason;
}

export type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;
```

Then force every consumer to handle all four, so adding a fifth status (say `paused`) breaks the build instead of silently falling through:

```ts
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

export function nextBillingEvent(sub: Subscription): Date | null {
  switch (sub.status) {
    case "trialing": return sub.trialEndsAt;
    case "active":   return sub.renewsAt;
    case "past_due": return sub.gracePeriodEndsAt;
    case "canceled": return null;
    default:         return assertNever(sub);
  }
}
```

**What this makes impossible (at the type rung):**
- Fields from the wrong state — `sub.retryCount` doesn't compile unless you've narrowed to `past_due`.
- Missing required fields — a `past_due` without a grace period won't construct.
- Swapping `customerId` and `planId` — the brands reject it.
- A `cancellation` that says voluntary but gives an involuntary reason — I nested `voluntary` *inside* the reason union so the two can't disagree. Swap my placeholder reason strings for your real ones.
- Forgetting a status in a switch — `assertNever` makes it a compile error.

**Consciously left possible:**
- `retryCount` can be negative or 3.5. A branded `NonNegativeInt` is overkill unless retry logic is load-bearing; a `CHECK (retry_count >= 0)` in the DB is the cheaper device.
- Illegal *transitions* (canceled → trialing) aren't expressed here — that's a separate `transition(sub, event)` function with its own exhaustive switch, not the data type.
- These types only hold if objects are **parsed** into them at the edge (DB row, Stripe webhook) — e.g. a `zod.discriminatedUnion("status", [...])` — otherwise a cast lets the 32-state bag back in.

One decision is yours: in the DB, do you store this as one table with nullable columns plus a `CHECK` per status, or a `status` column plus per-status side tables? The former is simpler; the latter makes the DB enforce what the TS type does. If you tell me your DB I can sketch the constraint.