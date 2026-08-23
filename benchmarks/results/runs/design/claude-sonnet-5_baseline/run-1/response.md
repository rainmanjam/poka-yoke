Quick misuse pass before the shape, per poka-yoke:

- **Optional-bag trap**: a flat `{status, trialEndsAt?, retryCount?, gracePeriodEndsAt?, cancelReason?, voluntary?, renewsAt?}` type permits `status: "active"` with a `cancelReason` sitting there, or `"canceled"` with a live `renewsAt`. 6 fields, most of them meaningless in most states.
- **New status added later**: someone adds `"paused"` next year — does every switch statement that handles subscriptions get a compile error, or does it silently fall into whatever the `default` branch does?
- **Swappable IDs**: `subscriptionId` and `customerId` are both strings — nothing stops `charge(customerId, subscriptionId)` from compiling backwards.
- **Cancellation is really two shapes wearing one skin**: "involuntary" (card declined, fraud) and "voluntary" (user clicked cancel) usually have different valid reasons and different downstream handling (dunning vs. exit survey). A flat `reason: string` doesn't stop someone writing `voluntary: true, reason: "payment_failed"`.

Here's the shape that makes those unsayable:

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId = Brand<string, "CustomerId">;

// Two nested unions, not two booleans-plus-strings — a payment-failure
// reason can't be paired with voluntary:true, and vice versa.
export type Cancellation =
  | { voluntary: true; reason: VoluntaryCancelReason }
  | { voluntary: false; reason: InvoluntaryCancelReason };

export type VoluntaryCancelReason =
  | "too_expensive"
  | "missing_features"
  | "switched_competitor"
  | "no_longer_needed"
  | "other";

export type InvoluntaryCancelReason =
  | "payment_failed"
  | "fraud_flagged"
  | "chargeback";

export type Subscription =
  | {
      status: "trialing";
      id: SubscriptionId;
      customerId: CustomerId;
      trialEndsAt: Date;
    }
  | {
      status: "active";
      id: SubscriptionId;
      customerId: CustomerId;
      renewsAt: Date;
    }
  | {
      status: "past_due";
      id: SubscriptionId;
      customerId: CustomerId;
      retryCount: number;
      gracePeriodEndsAt: Date;
    }
  | {
      status: "canceled";
      id: SubscriptionId;
      customerId: CustomerId;
      cancellation: Cancellation;
    };
```

Exhaustiveness so the compiler — not a person — catches a missed status:

```ts
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

function nextMilestone(sub: Subscription): Date | null {
  switch (sub.status) {
    case "trialing":  return sub.trialEndsAt;
    case "active":    return sub.renewsAt;
    case "past_due":  return sub.gracePeriodEndsAt;
    case "canceled":  return null;
    default:          return assertNever(sub);
  }
}
```

`nextMilestone` couldn't compile if it forgot a case, and it can't reach into `retryCount` from the `"active"` branch — TypeScript narrows the union per-branch.

At the API/DB boundary, parse rather than trust — a `zod` discriminated union rejects a malformed row instead of letting `any` carry it inward:

```ts
import { z } from "zod";

const SubscriptionSchema = z.discriminatedUnion("status", [
  z.object({ status: z.literal("trialing"), id: z.string(), customerId: z.string(), trialEndsAt: z.coerce.date() }),
  z.object({ status: z.literal("active"), id: z.string(), customerId: z.string(), renewsAt: z.coerce.date() }),
  z.object({ status: z.literal("past_due"), id: z.string(), customerId: z.string(), retryCount: z.number().int().nonnegative(), gracePeriodEndsAt: z.coerce.date() }),
  z.object({ status: z.literal("canceled"), id: z.string(), customerId: z.string(), cancellation: CancellationSchema }),
]);
```

`★ Insight ─────────────────────────────────────`
1. **Discriminated unions vs. optional bags** — TypeScript narrows on the literal `status` field, so inside `case "past_due"` the compiler *knows* `retryCount` and `gracePeriodEndsAt` exist and `renewsAt` doesn't. An optional-bag type gives you none of that — you'd be doing manual `if (sub.retryCount !== undefined)` checks everywhere, and nothing stops a caller from constructing the nonsense combination in the first place.
2. **Branding costs nothing at runtime** — `Brand<string, "X">` is a phantom type that only exists for `tsc`; it compiles to a plain string. You get compile-time protection against ID mix-ups for free, but only if `strict: true` + `tsc --noEmit` actually run in CI — a branded type in an unchecked repo is just a comment.
3. **Nesting `Cancellation` instead of two flat fields** is the same move one level down: it turns "voluntary + payment_failed" from a bug waiting to happen into a type error.
`─────────────────────────────────────────────────`

One thing left open on purpose: **legal state transitions aren't encoded here** (can you go `past_due` → `trialing`? probably not, but that's a business rule, not a shape rule). That's usually a `transition(sub, event)` function with a `never`-exhaustive switch over valid `(from, event)` pairs — worth doing once retry/dunning logic exists, not before.

The reason lists (`VoluntaryCancelReason` / `InvoluntaryCancelReason`) are placeholders — I don't know what your actual dunning/exit-survey flow tracks. That's a real decision: too few reasons and your churn analytics are useless, too many and support agents pick randomly. Could you fill in the real list (5-10 lines) for both unions based on what your cancellation flow / Stripe webhook already reports?