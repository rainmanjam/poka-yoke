Using **poka-yoke:design** to shape these types so the illegal combinations (a "trialing" sub with a cancel reason, a "canceled" sub still carrying a renewal date) can't be constructed at all.

**Misuse check first** (2 min, per the skill):
- Same-shaped fields sitting on one object → 4 optional fields, 2⁴ = 16 representable states, only 4 legal ones.
- A caller can read `.trialEndDate` off a sub that's actually `active` — TS won't stop them if it's just `trialEndDate?: Date`.
- Adding a 5th status next year (e.g. `paused`) should break the build everywhere it matters, not silently fall through a default branch.
- `voluntary` cancellations and `involuntary` ones likely have different valid reason codes — mixing them (`voluntary: true, reason: "chargeback"`) should be nonsense, not a valid value.

## The types

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export const SubscriptionId = (s: string): SubscriptionId => s as SubscriptionId;

// Voluntary and involuntary reasons are different sets — mixing them shouldn't typecheck.
type VoluntaryReason = "too_expensive" | "missing_features" | "no_longer_needed";
type InvoluntaryReason = "payment_failed_final" | "fraud_flagged" | "chargeback";

export type Cancellation =
  | { voluntary: true; reason: VoluntaryReason }
  | { voluntary: false; reason: InvoluntaryReason };

export type Subscription =
  | { id: SubscriptionId; status: "trialing"; trialEndDate: Date }
  | { id: SubscriptionId; status: "active"; renewalDate: Date }
  | { id: SubscriptionId; status: "past_due"; retryCount: number; gracePeriodEndDate: Date }
  | ({ id: SubscriptionId; status: "canceled"; canceledAt: Date } & Cancellation);
```

`status` is the discriminant: `sub.trialEndDate` is a compile error unless you've already narrowed to `status === "trialing"`. The compiler makes the check mandatory instead of a thing to remember.

Exhaustiveness, so a future 5th status can't slip past a `switch`:

```ts
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

function renewalCopy(sub: Subscription): string {
  switch (sub.status) {
    case "trialing":  return `Trial ends ${sub.trialEndDate.toDateString()}`;
    case "active":    return `Renews ${sub.renewalDate.toDateString()}`;
    case "past_due":  return `Retry ${sub.retryCount}, grace ends ${sub.gracePeriodEndDate.toDateString()}`;
    case "canceled":  return sub.voluntary ? `Canceled: ${sub.reason}` : `Lost: ${sub.reason}`;
    default:          return assertNever(sub);
  }
}
```

★ Insight ─────────────────────────────────────
- A bag-of-optionals design would let you construct `{status: "active", cancelReason: "fraud_flagged"}` and nothing would complain until it hit production logic that assumed active subs never have a reason. The union makes that combination have no spelling — Control rung, contact lens.
- `assertNever` isn't decoration — pair it with `@typescript-eslint/switch-exhaustiveness-check` and adding a `"paused"` status next year fails `tsc` at every switch that needs a new case, instead of quietly returning `undefined` from a `default`.
─────────────────────────────────────────────────

## What I deliberately left open

State *transitions* aren't in the type above — `Subscription` describes what a sub can look like, not what it's legal to move from/to. That's a billing-policy call, not a type-design one (can a `canceled` sub ever see `payment_succeeded` and reactivate, or is that always a new subscription? can `trialing` skip straight to `past_due`?). This is exactly the kind of decision I shouldn't guess at:

```ts
type Event =
  | { type: "trial_ended" }
  | { type: "payment_succeeded" }
  | { type: "payment_failed" }
  | { type: "grace_period_expired" }
  | { type: "canceled"; cancellation: Cancellation };

// TODO: encode which (status, event) pairs are legal per your billing policy.
// The signature forces every reachable branch to return a Subscription — so an
// event you haven't accounted for can't be silently swallowed into a no-op.
function transition(sub: Subscription, event: Event): Subscription {
  throw new Error("not implemented");
}
```

Could you fill in `transition`'s body for the pairs you know are legal today (e.g. `trialing` + `trial_ended` → `active` or `past_due` depending on whether a card's on file)? That matrix is the one place your actual cancellation/dunning policy needs to live, and it's more valuable coming from you than guessed by me.