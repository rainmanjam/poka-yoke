Applied poka-yoke's **design** mode (discriminated unions over bags of optionals is the textbook fit here). Quick misuse pass first:

- A flat `{status, trialEndDate?, renewalDate?, retryCount?, gracePeriodEndDate?, cancelReason?, voluntary?}` interface permits nonsense like an `active` sub with a `retryCount`, or a `canceled` sub missing `cancelReason`. It's 4 real states hiding inside what looks like ~2^6 possible shapes.
- `status` as a bare `string` lets a typo (`"Active"`, `"canceld"`) compile fine and fail silently at runtime.
- IDs (subscription, customer, plan) are all `string` — easy to pass one where another belongs.
- Adding a 5th status later should break every `switch` that needs updating, not fail silently.

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId = Brand<string, "CustomerId">;
export type PlanId = Brand<string, "PlanId">;

interface SubscriptionBase {
  id: SubscriptionId;
  customerId: CustomerId;
  planId: PlanId;
}

export type Subscription = SubscriptionBase &
  (
    | { status: "trialing"; trialEndDate: Date }
    | { status: "active"; renewalDate: Date }
    | { status: "past_due"; retryCount: number; gracePeriodEndDate: Date }
    | { status: "canceled"; cancelReason: CancelReason; voluntary: boolean }
  );

function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

// e.g. in a renewal job:
function nextActionDate(sub: Subscription): Date {
  switch (sub.status) {
    case "trialing": return sub.trialEndDate;
    case "active": return sub.renewalDate;
    case "past_due": return sub.gracePeriodEndDate;
    case "canceled": return sub.id as never; // no next action — compiler forces you to handle this
    default: return assertNever(sub);
  }
}
```

Rungs reached: the union makes reading `retryCount` off an `active` sub a **compile error** (Control, contact lens) — `sub.retryCount` doesn't type-check until you've narrowed on `sub.status === "past_due"`. The `assertNever` default arm gets you **Control on completeness**: add a 5th status and every switch that doesn't handle it fails the build instead of silently doing nothing. Branded IDs stop `customerId`/`planId`/`id` swaps at zero runtime cost.

What I deliberately left open: the `voluntary: boolean` + freeform `cancelReason` pair can still express nonsense — e.g. `voluntary: true, cancelReason: "payment_failed"`. That's a real mistake someone could make (a support tool writing the wrong flag), and it's fixable at Control by making `cancelReason` itself a union keyed off `voluntary`. I didn't design that union myself because the actual reason codes are a business decision you know and I don't — guessing them would just be different training-wheels prose baked into types instead of a doc comment.

`TODO` in the block above (`type CancelReason = ...`) — write it as a discriminated union split by voluntary/involuntary, e.g.:

```ts
type CancelReason =
  | { voluntary: true; reason: "too_expensive" | "no_longer_needed" | "switched_provider" }
  | { voluntary: false; reason: "payment_failed_max_retries" | "fraud_flagged" | "chargeback" };
```

if you drop that in and fold `voluntary` into it (removing the separate top-level field), the "voluntary cancel with an involuntary reason" mistake becomes unrepresentable too — that's the last piece I'd push to Control rather than leave as a convention.

One thing not modeled here: legal *transitions* (can `past_due` go straight to `active`, or must it pass through a payment retry?) — that's `guardrails`/state-machine territory, not the type shape. Say if you want that next.