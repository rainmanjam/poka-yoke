Write permission wasn't granted in this session, so here it is inline rather than as a file.

`★ Insight ─────────────────────────────────────`
- A record with four optional field groups advertises 2⁴ = 16 states; only 4 exist. A discriminated union on `status` is the difference between "the compiler knows `trialEndsAt` is absent when active" and "every call site re-checks."
- The two fields you described as one — `voluntary: boolean` + `cancelReason` — permit `{voluntary: true, reason: "payment_failed"}`. Nesting them makes that unsayable.
- The state most SaaS models are missing isn't in your list: *cancelled but paid through period end*. That's `active` with a flag, not `canceled`.
`─────────────────────────────────────────────────`

```ts
declare const brand: unique symbol
type Brand<T, B> = T & { readonly [brand]: B }

export type SubscriptionId = Brand<string, 'SubscriptionId'>
export type CustomerId    = Brand<string, 'CustomerId'>
export type RetryCount    = Brand<number, 'RetryCount'>

export function parseRetryCount(n: number): RetryCount {
  if (!Number.isInteger(n) || n < 0) throw new RangeError(`retryCount must be a non-negative integer, got ${n}`)
  return n as RetryCount
}

interface Core {
  readonly id: SubscriptionId
  readonly customerId: CustomerId
  readonly createdAt: Date
}

export interface Trialing extends Core {
  readonly status: 'trialing'
  readonly trialEndsAt: Date
  readonly hasPaymentMethod: boolean   // decides whether trial-end converts or lapses
}

export interface Active extends Core {
  readonly status: 'active'
  readonly renewsAt: Date
  readonly cancelAtPeriodEnd: boolean  // cancelled, still paid up — not `canceled`
}

export interface PastDue extends Core {
  readonly status: 'past_due'
  readonly retryCount: RetryCount
  readonly gracePeriodEndsAt: Date
  readonly failedRenewalAt: Date       // needed to bill correctly on recovery
}

export type Cancellation =
  | { kind: 'voluntary';   reason: 'too_expensive' | 'missing_features' | 'switched' | 'unneeded' | 'other'; feedback?: string }
  | { kind: 'involuntary'; reason: 'payment_failed' | 'chargeback' | 'fraud' | 'terms_violation' }

export interface Canceled extends Core {
  readonly status: 'canceled'
  readonly canceledAt: Date
  readonly accessEndsAt: Date          // access outlives cancellation; separate facts
  readonly cancellation: Cancellation
}

export type Subscription = Trialing | Active | PastDue | Canceled
export type SubscriptionStatus = Subscription['status']

export function assertNever(x: never): never {
  throw new Error(`Unhandled subscription state: ${JSON.stringify(x)}`)
}
```

The `assertNever` arm in every `switch` is the highest-leverage line here — add a fifth state next year and the build breaks at every site that must change, instead of silently hitting a `default`.

**What I left possible on purpose:** nothing stops you constructing a `PastDue` whose `gracePeriodEndsAt` precedes `failedRenewalAt`. Ordering invariants across two dates need either a smart constructor or a DB `CHECK`; the type system won't do it, and pushing it to Postgres means it holds for scripts and other services too.

## One piece I'd rather you wrote

The transition table is business policy, not type design, and guessing it would bake my assumptions into your billing:

```ts
export const LEGAL_TRANSITIONS: Readonly<Record<SubscriptionStatus, readonly SubscriptionStatus[]>> = {
  trialing: [ /* ? */ ],
  active:   [ /* ? */ ],
  past_due: [ /* ? */ ],
  canceled: [ /* ? */ ],
}
```

Four calls decide it: does `past_due` recover into `active` in place, or is recovery a new subscription? Can `trialing` fail its conversion charge straight into `past_due`, or must it pass through `active`? Is `canceled` terminal, or can someone reactivate? Can you grant a trial extension to an `active` sub?

Fill those in and I'll build `transition()` around it so an illegal move is rejected before the write — plus the near-miss tests that prove the rejection actually fires.