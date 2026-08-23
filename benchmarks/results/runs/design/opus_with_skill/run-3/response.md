Using **poka-yoke:design** (routed from the poka-yoke router; also read `references/lang-typescript.md` and the hazard catalog).

## The misuses I designed against

1. `{ status, trialEndsAt?, retryCount?, gracePeriodEnd?, cancelReason?, voluntary? }` — six optionals claim 64 states, ~4 are real. (C8)
2. `voluntary: boolean` next to a free-text `cancelReason` permits *"voluntary cancellation, reason: card_declined"*. (C2, C8)
3. `subscriptionId`/`customerId` both `string`, adjacent in every function. (C1)
4. `status: string` compared against literals, so a new state silently falls through every `if`. (C4/F1)
5. `sub.status = 'active'` assigned from 5 places — nothing stops `canceled → active`. (M3)
6. Entitlement checks written inline as `status === 'active' || status === 'trialing'`, differently in each file.

## The types

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId     = Brand<string, "CustomerId">;
export type PlanId         = Brand<string, "PlanId">;
/** ISO-8601, always UTC. Obtained by parsing, never by `new Date()` in business logic. */
export type Instant        = Brand<string, "Instant">;

type Core = {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
  readonly planId: PlanId;
  readonly startedAt: Instant;
};

export type Cancellation =
  | { readonly kind: "voluntary";
      readonly reason: "too_expensive" | "missing_feature" | "switched_provider"
                     | "no_longer_needed" | "other";
      readonly comment?: string }
  | { readonly kind: "involuntary";
      readonly reason: "dunning_exhausted" | "chargeback" | "fraud" | "compliance" };

export type Subscription =
  | (Core & { readonly status: "trialing"; readonly trialEndsAt: Instant })
  | (Core & { readonly status: "active";   readonly renewsAt: Instant })
  | (Core & { readonly status: "past_due";
              readonly retryCount: RetryCount;
              readonly gracePeriodEndsAt: Instant;
              readonly lastFailureAt: Instant })
  | (Core & { readonly status: "canceled";
              readonly canceledAt: Instant;
              readonly cancellation: Cancellation });

export type RetryCount = Brand<number, "RetryCount">; // 0..MAX_RETRIES, parsed
export const MAX_RETRIES = 4;
export const retryCount = (n: number): RetryCount => {
  if (!Number.isInteger(n) || n < 0 || n > MAX_RETRIES)
    throw new RangeError(`retryCount must be an integer 0..${MAX_RETRIES}, got ${n}`);
  return n as RetryCount;
};
```

`★ Insight ─────────────────────────────────────`
- The nested `Cancellation` union is the load-bearing bit: `voluntary` stops being a boolean *beside* the reason and becomes the **discriminant that selects which reasons exist**. "Voluntary + dunning_exhausted" now has no spelling — Control rung, contact lens.
- `trialEndsAt` etc. live *inside* the variant, so `sub.trialEndsAt` doesn't typecheck until you've narrowed to `"trialing"`. The compiler asks for the check you'd otherwise forget.
- Branding is erased at runtime — zero cost — but it's only load-bearing with `strict: true` and `tsc --noEmit` as a required CI check.
`─────────────────────────────────────────────────`

## One entitlement function, exhaustively matched

```ts
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription state: ${JSON.stringify(x)}`);
}

/** The single source of truth for "may this customer use the product right now?" */
export function isEntitled(sub: Subscription, now: Instant): boolean {
  switch (sub.status) {
    case "trialing": return now < sub.trialEndsAt;
    case "active":   return true;
    case "past_due": return now < sub.gracePeriodEndsAt; // ← policy, see question below
    case "canceled": return false;
    default:         return assertNever(sub);
  }
}
```

Add a fifth status next year and **the build breaks at every site that must change** — that `assertNever` arm is the cheapest high-leverage device in TypeScript. Enforce repo-wide with `@typescript-eslint/switch-exhaustiveness-check`.

## Transitions: one door, not five assignments

```ts
export type Event =
  | { type: "trial_converted";  renewsAt: Instant }
  | { type: "payment_failed";   gracePeriodEndsAt: Instant; at: Instant }
  | { type: "payment_retried_ok"; renewsAt: Instant }
  | { type: "canceled"; cancellation: Cancellation; at: Instant };

export type TransitionError = { code: "illegal_transition"; from: Subscription["status"]; event: Event["type"] };

export function transition(sub: Subscription, e: Event): Subscription | TransitionError { /* … */ }
```

Make the fields `readonly` (above) and export **no** setter, so `transition` is the only path to a new state — `canceled → active` becomes unreachable rather than merely discouraged (M3, Control).

At the boundary — your DB row and the Stripe webhook are both flat bags of nullable columns — parse **once** into `Subscription` (zod discriminated union) and never let the row shape into business logic. Back it with `CHECK` constraints so the nulls can't disagree with the status even from `psql`:

```sql
CHECK (status <> 'canceled' OR (canceled_at IS NOT NULL AND cancel_kind IS NOT NULL))
CHECK (status <> 'past_due' OR (retry_count IS NOT NULL AND grace_period_ends_at IS NOT NULL))
```

## Left deliberately possible

- **Reactivation.** `canceled` is terminal here; resubscribing mints a new `SubscriptionId`. Cleaner for revenue reporting, but it's a real product decision — say the word and I'll add a `reactivated` event instead.
- **Typestate** (a `Subscription<"active">` phantom parameter) would make illegal transitions a *compile* error rather than a runtime `TransitionError`. I didn't take it: subscription state arrives from a database at runtime, so the compiler can't know it anyway, and the generic parameter costs every caller readability. Warning rung, consciously.
- Nothing enforces that `gracePeriodEndsAt > lastFailureAt`. A `CHECK` in the schema is the cheap fix if you want it.

## One thing that's yours to decide

Two policy questions shape `isEntitled` and I've assumed answers rather than block on them:

1. **Does `past_due` retain access during the grace period?** I assumed yes (soft dunning — better retention, some free usage risk). Hard cutoff at first failure is the other valid answer.
2. **Is `trialing → past_due` legal?** I assumed no — a trial with no card converts straight to `canceled { involuntary, dunning_exhausted }`.

If you tell me your billing policy I'll encode it. Also: this repo is the poka-yoke plugin, not your SaaS — give me a path and I'll write these out as a real file with the transition table filled in.