★ Insight ─────────────────────────────────────
This is a textbook case of the "bag-of-optionals" hazard (C8). With separate optional fields per state, you'd permit 64 states when only 4 are real — and consumers would handle the nonsense states inconsistently.
─────────────────────────────────────────────────

Let me enumerate the misuses before proposing the types:

## How this design could go wrong

1. **Nonsense state combinations** — "trialing with a cancel_reason", "active with retry_count", "canceled with a renewal_date" — 60 of 64 possible states are meaningless if you use optional fields
2. **Unbounded retry** — what's the max? Can it be negative? Does 1000 failed retries mean something different than 3?
3. **Stringly-typed cancel reason** — free-form text means no exhaustive handling of cancellation types
4. **Voluntary/involuntary conflated with reason** — "voluntary: true, reason: payment-failed" is incoherent
5. **Non-exhaustive status handling** — adding a new status next year should break the build everywhere that needs updating, not silently fall through

## The mistake-proof design

```typescript
// Branded ID so subscription IDs can't be swapped with user IDs, etc.
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };
export type SubscriptionId = Brand<string, "SubscriptionId">;

// Bounded retry count - past this, the subscription should transition
type RetryCount = 0 | 1 | 2 | 3;

// Cancellation as a nested discriminated union - prevents "voluntary: true, reason: payment-failed"
type Cancellation =
  | { voluntary: true; reason: 'user-requested' | 'switched-provider' | 'downgrade' }
  | { voluntary: false; reason: 'payment-failed' | 'fraud' | 'terms-violation' };

// The subscription itself - discriminated union, not bag of optionals
export type Subscription =
  | { status: 'trialing'; trial_end_date: Date }
  | { status: 'active'; renewal_date: Date }
  | { status: 'past_due'; retry_count: RetryCount; grace_period_end: Date }
  | { status: 'canceled'; cancellation: Cancellation };

// Exhaustiveness helper - adding a new status breaks the build at every switch
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

// Example usage showing exhaustive handling
function getNextBillingDate(sub: Subscription): Date | null {
  switch (sub.status) {
    case 'trialing':
      return sub.trial_end_date;
    case 'active':
      return sub.renewal_date;
    case 'past_due':
      return sub.grace_period_end;
    case 'canceled':
      return null;
    default:
      return assertNever(sub); // Compile error if a status is missing
  }
}
```

## What this prevents

| Hazard | Device | Rung |
|--------|--------|------|
| "trialing with a cancel_reason" and 60 other nonsense states | Discriminated union — only 4 states are representable | **Control** |
| Unbounded or negative retry count | Literal union `0 \| 1 \| 2 \| 3` | **Control** |
| "voluntary: true, reason: payment-failed" | Nested discriminated union for cancellation | **Control** |
| Adding a status next year and forgetting to update handlers | `assertNever` + `@typescript-eslint/switch-exhaustiveness-check` | **Control** |
| Swapping subscription IDs with other IDs | Branded type | **Control** |

## What I consciously left possible

- **Free-form dates** — no validation that `trial_end_date` is in the future or that `grace_period_end` comes after the payment failure. TypeScript can't express "a Date that is in the future"; you'd need a runtime assertion at construction or a smart constructor.
- **Illegal state transitions** — nothing prevents going from `canceled` back to `trialing`. If that matters, add a transition function that's the only way to change status, and have it reject illegal moves.
- **No subscription ID on the type itself** — depending on how you use this, you might want `{ id: SubscriptionId } & Subscription` so the ID can't be forgotten.

Do you want me to add transition guards or tighten any of the date constraints?