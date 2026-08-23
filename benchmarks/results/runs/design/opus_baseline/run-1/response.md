I couldn't write the file — the Write to `private/subscription/subscription.ts` wasn't granted in this non-interactive session, so here it is inline. Grant it (or tell me where your SaaS repo is) and I'll drop it in.

First, the misuse enumeration the design is aimed at:

| Misuse | Made impossible? |
|---|---|
| `{status, trialEndsAt?, retryCount?, cancelReason?, voluntary?, renewsAt?}` — 6 optionals claim 64 states, 4 are real | Yes — discriminated union |
| Reading `sub.trialEndsAt` without checking status | Yes — inaccessible until narrowed |
| `voluntary: true` + `reason: "payment_failed"` | Yes — cancellation is its own union |
| Passing a `customerId` where a `subscriptionId` goes | Yes — branded types |
| Adding `paused` next year and silently falling through | Yes — `assertNever` |
| Negative / runaway `retryCount` | Yes — parsed, bounded 0–8 |
| Illegal transition (`canceled` → `active`) | Guard, rung 5 — needs your input, see below |

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId    = Brand<string, "CustomerId">;
export type PriceId       = Brand<string, "PriceId">;
export type RetryCount    = Brand<number, "RetryCount">;

export interface SubscriptionBase {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
  readonly priceId: PriceId;
  readonly createdAt: Date;
}

// voluntary/involuntary reasons are disjoint sets — a boolean + free string
// permits "voluntary: true, reason: dunning_exhausted". This doesn't.
export type Cancellation =
  | { readonly kind: "voluntary";   readonly reason: VoluntaryReason; readonly feedback?: string }
  | { readonly kind: "involuntary"; readonly reason: InvoluntaryReason };

export type VoluntaryReason =
  | "too_expensive" | "missing_features" | "switched_provider" | "no_longer_needed" | "other";
export type InvoluntaryReason =
  | "dunning_exhausted" | "payment_method_removed" | "fraud" | "compliance_hold";

export type SubscriptionState =
  | { readonly status: "trialing"; readonly trialEndsAt: Date }
  | { readonly status: "active";   readonly renewsAt: Date }
  | { readonly status: "past_due";
      readonly retryCount: RetryCount;
      readonly gracePeriodEndsAt: Date;
      readonly failedRenewalAt: Date }   // needed to bill correctly on recovery
  | { readonly status: "canceled";
      readonly canceledAt: Date;
      readonly cancellation: Cancellation;
      readonly accessEndsAt: Date };     // access usually runs to end of paid period

export type Subscription = SubscriptionBase & SubscriptionState;
export type SubscriptionStatus = SubscriptionState["status"];

export function assertNever(x: never): never {
  throw new Error(`Unhandled subscription variant: ${JSON.stringify(x)}`);
}

export function entitlementEndsAt(sub: Subscription): Date {
  switch (sub.status) {
    case "trialing": return sub.trialEndsAt;
    case "active":   return sub.renewsAt;
    case "past_due": return sub.gracePeriodEndsAt;
    case "canceled": return sub.accessEndsAt;
    default:         return assertNever(sub);
  }
}
```

`★ Insight ─────────────────────────────────────`
- `SubscriptionBase & SubscriptionState` distributes over the union, so `sub.status` narrowing still works — you get shared fields without repeating them in four variants.
- `readonly` everywhere isn't decoration: it makes `sub.status = "active"` a compile error, forcing every change through the transition function where the guard lives.
- The three added fields (`failedRenewalAt`, `accessEndsAt`, `canceledAt`) aren't scope creep — each is a value you'd otherwise reconstruct from an audit log at billing time.
`─────────────────────────────────────────────────`

**Parse at the boundary.** Stripe webhooks and Postgres rows are `unknown`. A matching Zod schema (`z.intersection(base, z.discriminatedUnion("status", [...]))`) with `.brand()` on the ids means the `as Subscription` cast lives in exactly one function and nowhere else. I have that written and will include it with the file.

**Prerequisite:** none of this holds without `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, and `tsc --noEmit` as a *required* CI check — plus `@typescript-eslint/switch-exhaustiveness-check` set to `error`, so the `assertNever` isn't optional discipline.

---

### One thing I need from you

I've stubbed the transition table and the guard that reads it:

```ts
export const LEGAL_TRANSITIONS: Readonly<
  Record<SubscriptionStatus, readonly SubscriptionStatus[]>
> = {
  trialing: [],   // TODO
  active:   [],   // TODO
  past_due: [],   // TODO
  canceled: [],   // TODO
};

export function transition(sub: Subscription, next: SubscriptionState): Subscription {
  if (!LEGAL_TRANSITIONS[sub.status].includes(next.status)) {
    throw new IllegalTransitionError(sub.status, next.status);
  }
  const { id, customerId, priceId, createdAt } = sub;
  return { id, customerId, priceId, createdAt, ...next };
}
```

Fill in the four arrays — this is your billing policy, not a typing question, and it's the one decision the type system can't make for you. Worth deciding deliberately:

- **`canceled → active`?** If reactivation is a real product feature, this edge exists and `canceled` is not terminal. If reactivation means "new subscription, new id", leave it empty and canceled becomes an absorbing state — which is far easier to reason about.
- **`trialing → past_due`?** Only if you take a payment method up front and the first charge can fail. If trials are card-free, a failed trial goes straight to `canceled`.
- **`past_due → trialing`?** Almost certainly never — but writing `[]` says so out loud.
- **`active → active`?** A renewal that just moves `renewsAt` forward. If you exclude it, every renewal has to route around this function.

Once that table is filled, it becomes the single source for the runtime guard, the property test, and a Postgres trigger — same rules, three enforcement points.

Two things I left possible on purpose, so they're a choice and not an oversight:

1. **`canceled` conflates "will cancel at period end" with "has canceled now."** A user who cancels mid-period is still `active` under this model, with no field saying so. If you support cancel-at-period-end (most SaaS do), that wants a fifth variant or a `pendingCancellation` field on `active`. Tell me and I'll add it.
2. **`Date` isn't branded**, so a local-time `Date` can reach a field expecting UTC. Cheap to add a `UtcInstant` brand; usually not worth it if everything comes through the parse layer already normalized.