Write permission wasn't granted for that path, so here it is inline.

## The shape

```ts
declare const brand: unique symbol;
type Brand<T, B extends string> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, 'SubscriptionId'>;
export type CustomerId     = Brand<string, 'CustomerId'>;
export type PlanId         = Brand<string, 'PlanId'>;

interface SubscriptionBase {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
  readonly planId: PlanId;
  readonly createdAt: Date;
}

export interface TrialingSubscription extends SubscriptionBase {
  readonly status: 'trialing';
  readonly trialEndsAt: Date;
}

export interface ActiveSubscription extends SubscriptionBase {
  readonly status: 'active';
  readonly renewsAt: Date;
}

export interface PastDueSubscription extends SubscriptionBase {
  readonly status: 'past_due';
  readonly retryCount: RetryCount;        // bounded, see below
  readonly gracePeriodEndsAt: Date;
  readonly enteredPastDueAt: Date;        // "how long past due" without a join
}

export interface CanceledSubscription extends SubscriptionBase {
  readonly status: 'canceled';
  readonly canceledAt: Date;
  readonly cancellation: Cancellation;    // the nested union, see below
}

export type Subscription =
  | TrialingSubscription | ActiveSubscription
  | PastDueSubscription  | CanceledSubscription;

export type SubscriptionStatus = Subscription['status'];
```

## The part that isn't obvious: cancellation

You described `canceled` as having *a reason* and *whether it was voluntary*. Those aren't two independent fields — a boolean beside a reason string lets you write `{ voluntary: true, reason: 'payment_failed' }`, which is nonsense that your churn dashboard will happily average. Make the reason vocabulary derive from the kind:

```ts
export type VoluntaryReason =
  | 'too_expensive' | 'missing_features' | 'switched_to_competitor'
  | 'no_longer_needed' | 'unused' | 'other';

export type InvoluntaryReason =
  | 'payment_failed' | 'fraud_suspected' | 'terms_violation' | 'chargeback';

export type Cancellation =
  | { readonly kind: 'voluntary';   readonly reason: VoluntaryReason; readonly feedback?: string }
  | { readonly kind: 'involuntary'; readonly reason: InvoluntaryReason };
```

`feedback` lives only on the branch where a human was actually present to give it.

## Bounded retry count

Dunning logic branches on this number, so an unbounded one lets a bug charge a dead card forever and a negative one silently disables the whole ladder:

```ts
export const MAX_PAYMENT_RETRIES = 4;
export type RetryCount = Brand<number, 'RetryCount'>;

export function parseRetryCount(n: number): RetryCount {
  if (!Number.isInteger(n) || n < 0 || n > MAX_PAYMENT_RETRIES) {
    throw new RangeError(`retryCount must be an integer in 0..${MAX_PAYMENT_RETRIES}, got ${n}`);
  }
  return n as RetryCount;
}
```

## The line that makes the union pay off

```ts
export function assertNever(value: never): never {
  throw new Error(`Unhandled subscription case: ${JSON.stringify(value)}`);
}

export function hasProductAccess(sub: Subscription, now: Date): boolean {
  switch (sub.status) {
    case 'trialing': return now < sub.trialEndsAt;
    case 'active':   return true;
    case 'past_due': return now < sub.gracePeriodEndsAt;
    case 'canceled': return false;
    default:         return assertNever(sub);
  }
}
```

Without that `default`, adding a `paused` state next year compiles clean and silently denies access everywhere. With it, the build breaks at every site that has to change. One line per switch; it's the highest-leverage thing in the file.

`★ Insight ─────────────────────────────────────`
- The union is only as strong as its weakest entry point. Your DB row has to be *one wide table with nullable columns* — SQL can't express the union — so the 128 illegal combinations still exist in `subscriptions`. Parse once at that boundary into `Subscription` and never let a raw row past it, or the union is decoration.
- Back it with per-status `CHECK` constraints in the migration. That device holds when someone connects with `psql` or ships a service in Go; the TypeScript one doesn't.
`─────────────────────────────────────────────────`

So you'd want a `parseSubscription(row: SubscriptionRow): Subscription` that switches on `row.status` and throws naming the missing column (`subscription ${id}: status=past_due requires grace_period_ends_at`). Note its `default` arm is a real `throw`, not `assertNever` — `row.status` is `string` there, and that's a genuine runtime boundary, not an exhaustiveness bug.

## Two things I left possible, deliberately

- **`retryCount` and `gracePeriodEndsAt` can disagree.** Nothing stops `retryCount: 4, gracePeriodEndsAt: <a year out>`. Encoding the dunning schedule in the type would need one state per rung, and that's past the point where the device pays for itself.
- **"Canceled" conflates two things** most billing systems separate: *cancel now* and *cancel at period end* (user churned, still has access until Friday). If you do the latter, `canceled` needs an `accessEndsAt`, or it's a fifth state. Worth deciding now — it's cheap today and a migration once you have callers.

## One decision I'd rather you make than guess at

The transitions are business rules, not type theory, and the wrong guess here is the kind that costs revenue. The signature I'd hang them on:

```ts
export interface IllegalTransition {
  readonly from: SubscriptionStatus;
  readonly to: SubscriptionStatus;
  readonly why: string;
}

// null = legal
export function checkTransition(
  from: SubscriptionStatus,
  to: SubscriptionStatus,
): IllegalTransition | null {
  // TODO
}
```

The four that actually matter, none with a universal answer:

1. **Trial ends with a card on file that then declines** — `trialing → past_due`, or `trialing → canceled(involuntary, payment_failed)`? This decides whether trial users get your grace period.
2. **`past_due → active` on a successful retry** — does `renewsAt` shift forward by the days spent past due, or stay on the original billing anchor? Shifting means dunning slowly walks everyone's billing date.
3. **`canceled → active`** — is reactivation a transition, or a new subscription row? A transition preserves history and destroys "when did this customer start"; a new row does the opposite.
4. **`active → trialing`** — almost certainly never, but write it down so nobody adds it as a convenience for a support tool.

Give me your calls on those (5–10 lines of switch is all it takes) and I'll wire it in with the `assertNever` arms.