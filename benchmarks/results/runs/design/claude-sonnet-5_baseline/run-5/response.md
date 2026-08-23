Applying the poka-yoke design ritual here: the risky shape is a single interface with `trialEndsAt?`, `renewalDate?`, `retryCount?`, `graceEndsAt?`, `cancelReason?`, `voluntary?` all optional — that permits nonsense like an active sub with a cancel reason, or a canceled sub with a retry count. A discriminated union makes those states unspellable instead of just "shouldn't happen."

```typescript
type SubscriptionId = string & { readonly __brand: 'SubscriptionId' };

interface TrialingSubscription {
  status: 'trialing';
  id: SubscriptionId;
  trialEndsAt: Date;
}

interface ActiveSubscription {
  status: 'active';
  id: SubscriptionId;
  renewsAt: Date;
}

interface PastDueSubscription {
  status: 'past_due';
  id: SubscriptionId;
  retryCount: number;
  gracePeriodEndsAt: Date;
}

interface CanceledSubscription {
  status: 'canceled';
  id: SubscriptionId;
  canceledAt: Date;
  cancellation: Cancellation;
}

type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;
```

One thing worth catching before it becomes a bug: "voluntary" and "reason" aren't independent. A reason of `payment_failed` paired with `voluntary: true` is meaningless, but a flat `{ reason: string; voluntary: boolean }` shape lets someone construct exactly that. Nest another union so the two reason vocabularies can't cross:

```typescript
type VoluntaryCancelReason = 'customer_requested' | 'switched_provider' | 'too_expensive';
type InvoluntaryCancelReason = 'payment_failed' | 'fraud_flagged' | 'chargeback';

type Cancellation =
  | { voluntary: true; reason: VoluntaryCancelReason }
  | { voluntary: false; reason: InvoluntaryCancelReason };
```

And an exhaustiveness guard so adding a fifth status (e.g. `paused`) breaks the build everywhere it needs to, instead of silently falling through some `if/else` chain:

```typescript
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

function daysUntilNextEvent(sub: Subscription): number {
  switch (sub.status) {
    case 'trialing': return daysBetween(new Date(), sub.trialEndsAt);
    case 'active': return daysBetween(new Date(), sub.renewsAt);
    case 'past_due': return daysBetween(new Date(), sub.gracePeriodEndsAt);
    case 'canceled': return 0;
    default: return assertNever(sub);
  }
}
```

`★ Insight ─────────────────────────────────────`
1. `status` is a **discriminant** — TS narrows the whole object's type once you check it in an `if`/`switch`, so inside `case 'past_due'` you get `retryCount` and `gracePeriodEndsAt` with no `?.` needed and no risk of reading `trialEndsAt` on an active sub.
2. The branded `SubscriptionId` (`string & { __brand }`) costs nothing at runtime but stops a `CustomerId` from being passed where a `SubscriptionId` belongs — a real bug class in billing code where lots of things are "just a string."
3. Nesting `Cancellation` as its own union instead of two loose fields is the same trick one level deeper: it shrinks the representable state space from 2 reasons × 2 booleans down to exactly the 2 combinations that are real.
`─────────────────────────────────────────────────`

What I deliberately left open: **which transitions between these four states are legal** (can `past_due` go straight to `canceled` without a grace period? can a canceled sub reactivate into `trialing` or does that require a brand-new subscription record?). That's a business rule only you know, and it's the part worth your input rather than mine. Sketch it as a function signature and I'll wire the exhaustiveness check around it:

```typescript
// TODO(you): return true only for transitions your billing logic actually allows.
function canTransition(from: Subscription['status'], to: Subscription['status']): boolean {
  // e.g. trialing -> active | canceled
  //      active   -> past_due | canceled
  //      past_due -> active | canceled
  //      canceled -> ??? (probably none — new subscription instead)
}
```

Want me to also generate a Zod schema mirroring this union for runtime validation at the API boundary (webhook payloads, DB reads)?