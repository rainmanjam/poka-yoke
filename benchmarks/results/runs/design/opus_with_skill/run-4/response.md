Write permission wasn't granted in this session, so here it is inline rather than as a file.

Using `poka-yoke:design` — you're defining a new interface, which is the cheapest moment to shape it.

## What I enumerated before writing the signature

| Misuse | Real? |
|---|---|
| Flat `{status, trialEndsAt?, retryCount?, gracePeriodEndsAt?, cancelReason?, voluntary?}` — 2⁶ spellings for 4 states | "active with a cancel reason", "canceled mid-retry" all typecheck |
| `voluntary: boolean` next to a free-text reason | permits `voluntary: true, reason: "chargeback"` |
| `subscriptionId`/`customerId`/`planId` all `string` | adjacent, swappable, compiles |
| Adding `paused` next year | must break the build, not fall through a `default` |
| `retryCount: number` | unbounded — a fifth charge, or dropping someone a cycle early |
| `new Date()` inside transition logic | grace-period boundaries are exactly what you need to test |

`★ Insight ─────────────────────────────────────`
The reason a discriminated union beats optional fields isn't tidiness — it's that `sub.trialEndsAt` becomes *inaccessible* until you narrow on `status`. The check can't be forgotten because the compiler asks for it at every read site, forever, for free.
`─────────────────────────────────────────────────`

## The types

```ts
declare const brand: unique symbol;
type Brand<T, B extends string> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId    = Brand<string, "CustomerId">;
export type PlanId        = Brand<string, "PlanId">;
export const SubscriptionId = (s: string): SubscriptionId => s as SubscriptionId;
// …same for the other two

export const MAX_PAYMENT_RETRIES = 4;
export type RetryCount = Brand<number, "RetryCount">;
export function retryCount(n: number): RetryCount {
  if (!Number.isInteger(n) || n < 0 || n > MAX_PAYMENT_RETRIES)
    throw new RangeError(`retryCount must be 0..${MAX_PAYMENT_RETRIES}, got ${n}`);
  return n as RetryCount;
}

// `voluntary: boolean` becomes a union, so the two reason vocabularies can't mix
export type Cancellation =
  | { readonly kind: "voluntary";   readonly reason: "too_expensive" | "missing_features"
        | "switched_to_competitor" | "no_longer_needed" | "other"; readonly comment?: string }
  | { readonly kind: "involuntary"; readonly reason: "payment_retries_exhausted"
        | "grace_period_expired" | "chargeback" | "fraud_suspected" };

interface SubscriptionCore {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
  readonly planId: PlanId;
  readonly startedAt: Date;
}

export interface TrialingSubscription extends SubscriptionCore {
  readonly status: "trialing";
  readonly trialEndsAt: Date;
}
export interface ActiveSubscription extends SubscriptionCore {
  readonly status: "active";
  readonly renewsAt: Date;
}
export interface PastDueSubscription extends SubscriptionCore {
  readonly status: "past_due";
  readonly retryCount: RetryCount;
  readonly gracePeriodEndsAt: Date;
}
export interface CanceledSubscription extends SubscriptionCore {
  readonly status: "canceled";
  readonly canceledAt: Date;        // added: billing will ask "were they canceled when this invoice ran?"
  readonly cancellation: Cancellation;
}

export type Subscription =
  | TrialingSubscription | ActiveSubscription | PastDueSubscription | CanceledSubscription;
```

## Exhaustiveness — one line per switch, highest leverage device in the language

```ts
export function assertNever(x: never): never {
  throw new Error(`Unhandled subscription variant: ${JSON.stringify(x)}`);
}

export function billingBannerFor(sub: Subscription): string {
  switch (sub.status) {
    case "trialing": return `Trial ends ${sub.trialEndsAt.toISOString()}`;
    case "active":   return `Renews ${sub.renewsAt.toISOString()}`;
    case "past_due": return `Attempt ${sub.retryCount + 1} — update card by ${sub.gracePeriodEndsAt.toISOString()}`;
    case "canceled": return sub.cancellation.kind === "voluntary" ? "Canceled" : "Canceled — billing problem";
    default:         return assertNever(sub);
  }
}
```

Add `@typescript-eslint/switch-exhaustiveness-check` at `error` so this can't be skipped on the next switch someone writes.

## Transitions — the source state goes in the signature

```ts
export function convertTrialToPaid(sub: TrialingSubscription, renewsAt: Date): ActiveSubscription
export function renew(sub: ActiveSubscription, renewsAt: Date): ActiveSubscription
export function paymentFailed(sub: ActiveSubscription | TrialingSubscription,
                              gracePeriodEndsAt: Date): PastDueSubscription
export function paymentRecovered(sub: PastDueSubscription, renewsAt: Date): ActiveSubscription
export function cancel(sub: TrialingSubscription | ActiveSubscription | PastDueSubscription,
                       cancellation: Cancellation, now: Date): CanceledSubscription
```

`renew(canceledSub, …)` and `paymentRecovered(trialSub, …)` don't typecheck. Nothing accepts a `CanceledSubscription`, which makes canceled terminal *by construction* — reactivation becomes a new subscription row. That's a real product commitment; flag it before you adopt this shape.

`now` is always a parameter, never `new Date()` inside — you can't test a grace-period boundary against a clock you can't move.

## Your call: the dunning exit

```ts
export type DunningOutcome =
  | { readonly next: "wait";         readonly subscription: PastDueSubscription }
  | { readonly next: "retry_charge"; readonly subscription: PastDueSubscription }
  | { readonly next: "cancel";       readonly subscription: CanceledSubscription };

// TODO(you): ~8 lines
export function advanceDunning(sub: PastDueSubscription, now: Date): DunningOutcome
```

Two clocks disagree and only you know which wins: `retryCount` hits `MAX_PAYMENT_RETRIES` while `gracePeriodEndsAt` is still in the future, versus the grace period expiring with retries left. Both exits are involuntary cancellations, but `payment_retries_exhausted` and `grace_period_expired` are different churn-report rows and probably different emails. Returning a union rather than `CanceledSubscription | null` means the caller can't forget the cancel branch.

## The boundary

These values arrive from Stripe webhooks as `any`. Parse once with `z.discriminatedUnion("status", […])`, `.transform()`-ing into the branded constructors, and let nothing else in the codebase construct a `Subscription` from raw JSON. Without that, every guarantee above is decoration.

## Left deliberately possible

- **`as` casts** bypass the brands. Lint `as unknown as T` at error level.
- **Transitions aren't enforced in the database.** A row-level `CHECK` can't see the previous state, so `shipped → pending` needs a trigger or a transition table. Application-only is fine until a second service or a `psql` session writes to this table.
- **No idempotency key on the transitions.** If these run from a queue consumer, `paymentFailed` fired twice is two `past_due` writes — worth a required key backed by a unique index (`M2` in the hazard catalog) once they're wired to webhook delivery.