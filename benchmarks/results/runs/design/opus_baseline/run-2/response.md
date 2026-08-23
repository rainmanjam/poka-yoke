Using **poka-yoke:design** — this is a "make invalid states unrepresentable" problem, which is exactly what that skill front-loads.

## Misuse I enumerated first

1. The obvious shape — `{status, trialEndsAt?, retryCount?, gracePeriodEndsAt?, cancelReason?, voluntary?}` — claims 2⁶ = 64 legal states. Four are real. It permits "active with a cancel reason" and "canceled with a retry count."
2. Adjacent same-typed dates: `trialEndsAt` / `gracePeriodEndsAt` / `renewsAt` are all `Date`. Swappable at every call site without complaint.
3. `voluntary: boolean` alongside a free-form reason permits `{voluntary: true, reason: "payment_failed"}`.
4. Next year someone adds `paused` or `incomplete`. Nothing breaks — the code silently falls through.

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId     = Brand<string, "CustomerId">;
export type PlanId         = Brand<string, "PlanId">;

// Same runtime type, different roles — the compiler now refuses the swap.
export type TrialEndsAt       = Brand<Date, "TrialEndsAt">;
export type RenewsAt          = Brand<Date, "RenewsAt">;
export type GracePeriodEndsAt = Brand<Date, "GracePeriodEndsAt">;
export type RetryCount        = Brand<number, "RetryCount">;   // parse: integer, 0 ≤ n ≤ MAX_RETRIES

export type VoluntaryReason   = "too_expensive" | "missing_features" | "switched_provider" | "other";
export type InvoluntaryReason = "payment_failed" | "fraud" | "compliance";

export type Cancellation =
  | { readonly kind: "voluntary";   readonly reason: VoluntaryReason; readonly feedback?: string }
  | { readonly kind: "involuntary"; readonly reason: InvoluntaryReason };

export type SubscriptionState =
  | { readonly status: "trialing"; readonly trialEndsAt: TrialEndsAt }
  | { readonly status: "active";   readonly renewsAt: RenewsAt }
  | { readonly status: "past_due"; readonly retryCount: RetryCount;
      readonly gracePeriodEndsAt: GracePeriodEndsAt }
  | { readonly status: "canceled"; readonly canceledAt: Date;
      readonly cancellation: Cancellation };

export type Subscription = {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
  readonly planId: PlanId;
  readonly createdAt: Date;
} & SubscriptionState;
```

Every read site is now forced through a narrow:

```ts
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription state: ${JSON.stringify(x)}`);
}

export function billingBanner(sub: Subscription): string {
  switch (sub.status) {
    case "trialing": return `Trial ends ${sub.trialEndsAt.toDateString()}`;
    case "active":   return `Renews ${sub.renewsAt.toDateString()}`;
    case "past_due": return `Payment failed ${sub.retryCount}× — access ends ${sub.gracePeriodEndsAt.toDateString()}`;
    case "canceled": return sub.cancellation.kind === "voluntary" ? "Canceled" : "Canceled for non-payment";
    default:         return assertNever(sub);
  }
}
```

`sub.retryCount` doesn't exist until you've narrowed to `past_due` — the check can't be forgotten, because the compiler asks for it.

`★ Insight ─────────────────────────────────────`
- Nesting `Cancellation` as its own union instead of flattening `voluntary: boolean` + `reason: string` is the highest-value move here: it makes "voluntary cancellation for payment_failed" unspellable, which a boolean flag can never do.
- The `default: assertNever(sub)` arm is what converts adding `"paused"` next year from a silent fallthrough into a build failure at every site that must change. One line per switch. Turn on `@typescript-eslint/switch-exhaustiveness-check` so nobody omits it.
`─────────────────────────────────────────────────`

## Two things this does *not* fix

**Types vanish at runtime.** A row read straight from Postgres is `any`-shaped. Parse at the boundary (zod discriminated union on `status`), and mirror the invariant in the schema so a `psql` session or a second service can't write a nonsense row:

```sql
CHECK (
  (status = 'active'   AND renews_at IS NOT NULL AND cancel_reason IS NULL AND retry_count IS NULL) OR
  (status = 'past_due' AND retry_count IS NOT NULL AND grace_period_ends_at IS NOT NULL) OR
  -- …
)
```

**Illegal *transitions* are still expressible.** Nothing above stops `canceled → past_due`. That needs a motion-step device — and it's the one place your domain knowledge beats mine.

## Your turn — the transition table

This is where the real business decisions live, and I'd be guessing:

```ts
// TODO(you): 5–10 lines.
export function transition(from: Subscription, event: SubscriptionEvent): Subscription
```

The questions that shape it:
- Does `canceled` reactivate into `active`, or does reactivation mint a *new* subscription? (Affects whether canceled is terminal — if it is, model it as an absorbing state and the table gets much smaller.)
- Can `past_due` return to `active` on a successful retry, or does it go to `trialing` on a plan change?
- What happens at `gracePeriodEndsAt` — auto-cancel involuntary, or does a human decide?

Write the legal pairs and I'll turn them into a typed transition function where the illegal ones don't compile.

Want me to drop this into a file? Tell me the repo path — I didn't want to write it into `poke_yoke/`, since that's a different project.