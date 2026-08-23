Read the router, `design`, plus `references/hazard-catalog.md` and `references/lang-typescript.md`. Your SaaS code isn't in this repo, so I've kept the design inline rather than dropping a file into the poka-yoke tree — say the word and the path and I'll write it there.

## Misuse enumeration (the ritual, before the signature)

| # | Mistake someone could plausibly make | Hazard |
|---|---|---|
| 1 | Read `sub.trialEndsAt` on a canceled sub, get `undefined`, treat as "no trial" | C8 bag-of-optionals |
| 2 | Construct `{status:"canceled", retryCount: 3, trialEndsAt: ...}` — nonsense that compiles | C8 |
| 3 | `wasVoluntary: true` alongside `reason: "payment_failed"` | C2 boolean flag |
| 4 | Add `paused` next quarter; every `switch` silently falls to `default` | F1 |
| 5 | Assign `status = "active"` on a canceled sub from some webhook handler | M3 illegal transition |
| 6 | Pass a `customerId` where a `subscriptionId` is expected | C3/C1 |
| 7 | Dunning loop retries forever — `retryCount` has no ceiling in the type | F7 |
| 8 | Local `new Date()` in grace-period math; wrong for half your customers | C9 |

`{status, trialEndsAt?, retryCount?, gracePeriodEndsAt?, cancelReason?, wasVoluntary?, renewsAt?}` claims **2⁶ = 64 states**. Four are real.

## The types

```ts
// ── Identity: contact lens. transfer(subId, custId) must not compile. ──
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId     = Brand<string, "CustomerId">;
export type PlanId         = Brand<string, "PlanId">;
export type UserId         = Brand<string, "UserId">;

/** UTC ISO-8601. Obtain from an injected clock — never `new Date()` in domain logic. */
export type Instant = Brand<string, "Instant">;

// ── Dunning: bounded by construction, not by a comment. ──
export const MAX_DUNNING_ATTEMPTS = 4;
export type DunningAttempt = Brand<number, "DunningAttempt">;

export const firstAttempt = (): DunningAttempt => 1 as DunningAttempt;

/** Returns "exhausted" instead of an out-of-range attempt, so the caller
 *  is forced to decide what happens at the cap. */
export const nextAttempt = (a: DunningAttempt): DunningAttempt | "exhausted" =>
  a >= MAX_DUNNING_ATTEMPTS ? "exhausted" : ((a + 1) as DunningAttempt);

// ── Cancellation: voluntariness is the discriminant, not a sibling boolean. ──
export type Cancellation =
  | { readonly kind: "voluntary";
      readonly reason: "too_expensive" | "missing_features" | "switched_provider"
                     | "no_longer_needed" | "other";
      readonly canceledAt: Instant;
      readonly canceledBy: UserId }              // an actor exists only here
  | { readonly kind: "involuntary";
      readonly reason: "dunning_exhausted" | "fraud_suspected" | "chargeback" | "compliance";
      readonly canceledAt: Instant };

// ── The state itself ──
interface SubscriptionCore {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
  readonly planId: PlanId;
  readonly createdAt: Instant;
}

export type Subscription = SubscriptionCore & (
  | { readonly status: "trialing";
      readonly trialEndsAt: Instant }
  | { readonly status: "active";
      readonly renewsAt: Instant }
  | { readonly status: "past_due";
      readonly attempt: DunningAttempt;
      readonly gracePeriodEndsAt: Instant;
      readonly lastFailureAt: Instant }
  | { readonly status: "canceled";
      readonly cancellation: Cancellation;
      readonly accessEndsAt: Instant }           // paid-through date ≠ canceledAt
);

export type SubscriptionStatus = Subscription["status"];
```

`★ Insight ─────────────────────────────────────`
- `SubscriptionCore & (…union…)` keeps shared fields written once while still narrowing: `if (sub.status === "past_due")` gives you `attempt` *and* `customerId`. A union of four fully-spelled interfaces works too but duplicates the core on every variant.
- `canceledBy: UserId` living only on the `voluntary` arm is the same move as the status union, one level down — an involuntary cancellation has no human actor, so the field has no spelling there.
- `readonly` everywhere is what makes the transition function below the *only* path to a new state. Without it, `sub.status = "active"` stays available and the whole state machine is advisory.
`─────────────────────────────────────────────────`

## Exhaustiveness — the device that pays every time you add a status

```ts
export function assertNever(x: never): never {
  throw new Error(`Unhandled subscription variant: ${JSON.stringify(x)}`);
}

export function isEntitled(sub: Subscription, now: Instant): boolean {
  switch (sub.status) {
    case "trialing": return now < sub.trialEndsAt;
    case "active":   return true;
    case "past_due": return now < sub.gracePeriodEndsAt;  // grace = still served
    case "canceled": return now < sub.accessEndsAt;       // paid through period end
    default:         return assertNever(sub);
  }
}
```

Add `"paused"` to the union and this fails to compile — along with every other billing decision in the codebase. Enforce repo-wide with `@typescript-eslint/switch-exhaustiveness-check` at `error`.

## The transition function — and one decision that's yours

Because every field is `readonly`, the only way to reach a new state is through one function. Which makes *its* table the single place the state machine lives:

```ts
export type SubscriptionEvent =
  | { readonly type: "trial_converted";   readonly at: Instant; readonly renewsAt: Instant }
  | { readonly type: "payment_succeeded"; readonly at: Instant; readonly renewsAt: Instant }
  | { readonly type: "payment_failed";    readonly at: Instant; readonly gracePeriodEndsAt: Instant }
  | { readonly type: "canceled";          readonly at: Instant; readonly cancellation: Cancellation };

export type TransitionResult =
  | { readonly ok: true;  readonly next: Subscription }
  | { readonly ok: false; readonly from: SubscriptionStatus; readonly event: SubscriptionEvent["type"] };

/**
 * TODO(you): the legal (status, event) pairs.
 *
 * Switch on `sub.status`, then on `event.type`; return `{ok: false, ...}` for
 * anything not listed. Use assertNever on both switches so a new status or a
 * new event breaks the build here first.
 */
export function transition(sub: Subscription, event: SubscriptionEvent): TransitionResult {
  // ...
}
```

I've deliberately not filled this in, because the four open questions are business calls, not type calls, and they're the ones that bite in production:

1. **`canceled` → anything?** If a churned customer resubscribes, is that a transition back to `active`, or a brand-new `Subscription` row? (New row is usually right — it keeps revenue reporting and trial-eligibility honest — but it means `canceled` is terminal and your reactivation flow needs a different entry point.)
2. **`trialing` → `past_due` directly?** Only matters if you take a card up front. If you don't, trial expiry goes straight to `canceled`/involuntary and `past_due` is unreachable from `trialing`.
3. **`past_due` → `active` on `payment_succeeded`** — presumably yes. But does a *second* `payment_failed` while already `past_due` extend `gracePeriodEndsAt`, or hold the original deadline? Extending it is how subscriptions live in grace forever.
4. **What does `nextAttempt` returning `"exhausted"` do?** Almost certainly emit `canceled` with `reason: "dunning_exhausted"` — but that's the one place your cancel flow fires without a human, so it's worth stating explicitly.

Five to ten lines from you on those four and the table writes itself.

## Push it down to the database (F6)

Types vanish at runtime; the columns don't. Two constraints carry the same invariants for anything that touches the table — scripts, `psql`, a Go service later:

```sql
ALTER TABLE subscriptions ADD CONSTRAINT status_fields_match CHECK (
  CASE status
    WHEN 'trialing' THEN trial_ends_at IS NOT NULL AND renews_at IS NULL
                         AND attempt IS NULL AND cancel_reason IS NULL
    WHEN 'active'   THEN renews_at IS NOT NULL AND trial_ends_at IS NULL
                         AND attempt IS NULL AND cancel_reason IS NULL
    WHEN 'past_due' THEN attempt BETWEEN 1 AND 4 AND grace_period_ends_at IS NOT NULL
                         AND cancel_reason IS NULL
    WHEN 'canceled' THEN cancel_reason IS NOT NULL AND cancel_kind IS NOT NULL
                         AND (cancel_kind = 'voluntary') = (canceled_by IS NOT NULL)
  END
);

-- One live subscription per customer.
CREATE UNIQUE INDEX one_live_sub_per_customer ON subscriptions (customer_id)
  WHERE status IN ('trialing', 'active', 'past_due');
```

Note the honest limit from the catalog: a row-level `CHECK` sees one row's values, not where that row came from. It cannot forbid `canceled → active`. Policing *transitions* in the database needs a trigger or a transition table — worth it only if something other than this TypeScript writes the column.

## What I left possible, on purpose

- **Money isn't modeled.** You didn't ask, but `amount: number` on the adjacent invoice type is C6 and will cost you a reconciliation weekend. Integer minor units + currency in the type.
- **Nothing stops `new Date()`** leaking into grace-period math. `Instant` is branded but a lint rule (`no-restricted-syntax` on `NewExpression[callee.name="Date"]`) is what actually enforces the injected clock — Warning rung, not Control.
- **`Subscription` isn't parsed at the boundary.** The union is a compile-time claim; a row from Postgres or a Stripe webhook is `any` until a zod schema says otherwise. `z.discriminatedUnion("status", [...])` mirrors this shape almost exactly and is where it becomes real.
- **No transition history.** The union models the *current* state only. If billing support ever asks "when did this go past_due the first time", you need an append-only event table, not more fields.

Rungs reached: **Control** on hazards 1, 2, 3, 4, 6, 7 (types + DB constraints); **Control** on 5 via `readonly` + single transition function, degrading to **Warning** if another service writes the table directly; **Warning** on 8, since TypeScript can't stop a clock read.