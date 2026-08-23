Write access to the repo is denied, so here it is inline — move it into your SaaS repo when you're ready.

`★ Insight ─────────────────────────────────────`
- The tell that a flat shape is wrong: count the optional fields. `{status, trialEndsAt?, retryCount?, gracePeriodEndsAt?, cancelReason?, voluntary?}` claims 2⁶ = 64 legal states. Exactly 4 exist.
- `voluntary: boolean` + `reason: string` is the same bug one level down — it permits `{voluntary: true, reason: "payment_failed"}`. The two reason sets are disjoint, so they belong on a discriminant.
- TypeScript is structurally typed, so `type CustomerId = string` buys you nothing. Branding costs zero at runtime and makes `charge(planId, customerId)` a compile error.
`─────────────────────────────────────────────────`

## The core

```ts
declare const brand: unique symbol;
type Brand<T, B extends string> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId    = Brand<string, "CustomerId">;
export type PlanId        = Brand<string, "PlanId">;
export type RetryCount    = Brand<number, "RetryCount">;

export const RetryCount = (n: number): RetryCount => {
  if (!Number.isInteger(n) || n < 0) throw new RangeError(`RetryCount: ${n}`);
  return n as RetryCount;
};

interface SubscriptionCore {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
  readonly planId: PlanId;
  readonly createdAt: Date;
}

// Cancellation reasons are disjoint sets — nest the union rather than
// pairing a boolean with a free-text string.
export type Cancellation =
  | { readonly kind: "voluntary";
      readonly reason: "too_expensive" | "missing_features" | "switched_competitor" | "no_longer_needed" | "other";
      readonly feedback?: string }          // allowed *alongside* a reason, never instead of one
  | { readonly kind: "involuntary";
      readonly reason: "payment_failed" | "chargeback" | "fraud_suspected" | "compliance_hold" };

export type Subscription =
  | (SubscriptionCore & { readonly status: "trialing"; readonly trialEndsAt: Date })
  | (SubscriptionCore & { readonly status: "active";   readonly renewsAt: Date })
  | (SubscriptionCore & { readonly status: "past_due";
                          readonly retryCount: RetryCount;
                          readonly gracePeriodEndsAt: Date;
                          readonly failedAt: Date })     // needed to reconcile against the PSP
  | (SubscriptionCore & { readonly status: "canceled";
                          readonly canceledAt: Date;
                          readonly cancellation: Cancellation });

export type SubscriptionStatus = Subscription["status"];
export type SubscriptionOf<S extends SubscriptionStatus> = Extract<Subscription, { status: S }>;
```

`SubscriptionOf<"past_due">` is what you give to a function that only handles dunning — it can't be called with an active sub.

## Exhaustiveness

One line per switch, and adding a fifth status breaks the build at every site that must change. Turn on `@typescript-eslint/switch-exhaustiveness-check` as `error` so nobody omits the arm.

```ts
export function assertNever(x: never): never {
  throw new Error(`Unhandled subscription variant: ${JSON.stringify(x)}`);
}

export function hasAccess(sub: Subscription, now: Date): boolean {
  switch (sub.status) {
    case "trialing": return sub.trialEndsAt > now;
    case "active":   return true;
    case "past_due": return sub.gracePeriodEndsAt > now;   // still served during grace
    case "canceled": return false;
    default:         return assertNever(sub);
  }
}
```

Derive entitlement in exactly one place. Otherwise it gets reimplemented per call site and one of them forgets that past_due-inside-grace still gets the product.

## What this leaves possible

- **Illegal transitions.** The types stop you *reading* `trialEndsAt` off a canceled sub; they don't yet stop you *writing* `canceled → active`. Fixing that is the next section.
- **Stale dates.** Nothing enforces `gracePeriodEndsAt > failedAt`. Add a `CHECK` constraint in Postgres — that holds even when someone runs a script or connects with `psql`.
- **Runtime boundary.** These types vanish at compile time. Anything arriving from Stripe webhooks or your DB driver needs a Zod parse before it's a `Subscription`.

## Your call: the transition table

This is the decision that shapes the model, and it's yours — it's billing policy, not typing. The shape:

```ts
// transitions.ts
/**
 * Each transition consumes one concrete state and returns another, so an
 * illegal move is a compile error rather than a runtime guard someone skips.
 */
export function recoverPayment(sub: SubscriptionOf<"past_due">, renewsAt: Date): ActiveSubscription;
export function exhaustRetries(sub: SubscriptionOf<"past_due">, at: Date): CanceledSubscription;

// TODO(you): fill these in — the answers decide the signatures above.
//  1. Can a trial go straight to past_due (card declines at trial end), or
//     must it pass through active first? Affects whether trialing needs a
//     payment-method-on-file flag.
//  2. Is reactivation after cancel a *transition* or a brand-new subscription
//     row? If it's a transition, canceled stops being terminal and you need
//     `reactivate(sub: CanceledSubscription): ActiveSubscription`.
//  3. Voluntary cancel while past_due — does it record the voluntary reason,
//     or does the outstanding balance make it involuntary?
```

Question 2 is the one that bites: if reactivation is a transition, `canceled` isn't terminal and your revenue reporting has to handle a subscription with two lifetimes. Most teams make it a new row. Which way do you want it?