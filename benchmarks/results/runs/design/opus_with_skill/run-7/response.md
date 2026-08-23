Routing: this is `design` mode (new interface, "what should the types look like") — I read the router, `skills/design/SKILL.md`, the hazard catalog, and `references/lang-typescript.md`.

## First, the misuse list (this is what decides the shape)

1. A single flat record `{ status, trialEndsAt?, retryCount?, gracePeriodEndsAt?, cancelReason?, voluntary? }` has 5 optionals — it claims 32 states are legal when 4 are. It permits `active` with a cancel reason, and `canceled` with no reason at all. (**C8**)
2. `voluntary: boolean` next to a free-text reason permits `{ voluntary: true, reason: "dunning_exhausted" }` — a churn dashboard reading either field alone gets a different answer. (**C2**)
3. `status: string` means a typo compiles, and adding `paused` next year silently falls through every `if/else`. (**C4/F1**)
4. `sub.status = "canceled"` assigned from five call sites means every one of them has to know the whole machine. Reviving a canceled sub to `active` must not typecheck. (**M3**)
5. IDs as bare `string` — `getSubscription(customerId)` compiles. (**C1**)
6. The Stripe webhook hands you `any`. (**C7**)

## The types

```ts
// ── ids.ts ────────────────────────────────────────────────────────────────
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId     = Brand<string, "CustomerId">;
export type PlanId         = Brand<string, "PlanId">;

// ── subscription.ts ───────────────────────────────────────────────────────
export const MAX_DUNNING_RETRIES = 4;
export type RetryCount = Brand<number, "RetryCount">;

/** Parse, don't validate: a RetryCount cannot exist out of range. */
export function retryCount(n: number): RetryCount {
  if (!Number.isInteger(n) || n < 0 || n > MAX_DUNNING_RETRIES) {
    throw new RangeError(`retryCount must be an integer 0..${MAX_DUNNING_RETRIES}, got ${n}`);
  }
  return n as RetryCount;
}

export type VoluntaryReason   = "too_expensive" | "missing_features" | "switched_product" | "no_longer_needed" | "other";
export type InvoluntaryReason = "dunning_exhausted" | "payment_method_expired" | "chargeback" | "fraud";

/** Two axes that were one boolean + one string. Now they cannot disagree. */
export type Cancellation =
  | { readonly kind: "voluntary";   readonly reason: VoluntaryReason; readonly requestedBy: CustomerId; readonly note?: string }
  | { readonly kind: "involuntary"; readonly reason: InvoluntaryReason };

type Core = {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
  readonly planId: PlanId;
  readonly startedAt: Date; // UTC instant, never a local wall-clock string
};

export type Subscription = Core & (
  | { readonly status: "trialing"; readonly trialEndsAt: Date }
  | { readonly status: "active";   readonly renewsAt: Date }
  | { readonly status: "past_due"; readonly retryCount: RetryCount; readonly gracePeriodEndsAt: Date }
  | { readonly status: "canceled"; readonly canceledAt: Date; readonly cancellation: Cancellation }
);

export type Status = Subscription["status"];
export type SubscriptionIn<S extends Status> = Extract<Subscription, { status: S }>;
```

`readonly` everywhere is load-bearing: it means no call site can reach in and assign `status`, so the transition function below is the *only* way a subscription changes state.

```ts
export function assertNever(x: never): never {
  throw new Error(`Unhandled subscription variant: ${JSON.stringify(x)}`);
}

export function accessEndsAt(s: Subscription): Date {
  switch (s.status) {
    case "trialing": return s.trialEndsAt;        // .renewsAt is not in scope here
    case "active":   return s.renewsAt;
    case "past_due": return s.gracePeriodEndsAt;
    case "canceled": return s.canceledAt;
    default:         return assertNever(s);       // adding "paused" breaks the build here
  }
}
```

★ Insight ─────────────────────────────────────
- The intersection `Core & (A | B | C | D)` distributes, so narrowing on `s.status` still works — you get shared fields without repeating them and without weakening the union.
- `assertNever` is the whole reason to prefer this over an enum + optional fields: it converts "we forgot to handle the new state" from a production incident into a compile error, at one line per switch.
─────────────────────────────────────────────────

## Where the device has to live outside TypeScript

Types vanish at runtime, so the same invariant needs restating twice:

```ts
// Boundary (Stripe webhook, DB row hydration) — nothing enters the app unparsed.
const SubscriptionRow = z.discriminatedUnion("status", [
  z.object({ status: z.literal("trialing"), trial_ends_at: z.coerce.date(), /* … */ }),
  z.object({ status: z.literal("past_due"), retry_count: z.number().int().min(0).max(MAX_DUNNING_RETRIES), grace_period_ends_at: z.coerce.date(), /* … */ }),
  // …
]);
```

```sql
-- Postgres: the union, restated where every service and every psql session sees it (F6)
ALTER TABLE subscriptions ADD CONSTRAINT status_shape CHECK (
  CASE status
    WHEN 'trialing' THEN trial_ends_at IS NOT NULL AND cancel_kind IS NULL AND retry_count IS NULL
    WHEN 'active'   THEN renews_at     IS NOT NULL AND cancel_kind IS NULL AND retry_count IS NULL
    WHEN 'past_due' THEN retry_count BETWEEN 0 AND 4 AND grace_period_ends_at IS NOT NULL
    WHEN 'canceled' THEN canceled_at IS NOT NULL AND cancel_kind IS NOT NULL AND cancel_reason IS NOT NULL
  END
);
```

## The one decision I'm not making for you

I've prepared the transition function, but the legal-transition table is a business rule, not a typing exercise — only you know whether a canceled subscription can be revived in place or must become a new row, and whether a failed trial goes to `past_due` or straight to `canceled`.

```ts
type Event =
  | { type: "trial_ended";      renewsAt: Date }
  | { type: "payment_failed";   gracePeriodEndsAt: Date }
  | { type: "payment_recovered"; renewsAt: Date }
  | { type: "canceled";         at: Date; cancellation: Cancellation };

export type TransitionError = { code: "illegal_transition"; from: Status; event: Event["type"] };

/**
 * The ONLY path to a new state. Every field is readonly so nothing else can assign one.
 * TODO(you): fill in the match. Decisions I deliberately left open —
 *   - trialing + payment_failed → past_due, or canceled (no card on file yet)?
 *   - past_due + payment_failed at retryCount === MAX_DUNNING_RETRIES → canceled/involuntary?
 *   - canceled + anything → always illegal, or is in-place reactivation allowed?
 */
export function transition(s: Subscription, e: Event): Subscription | TransitionError {
  // 5-10 lines: switch on `${s.status}:${e.type}`, return the new value or the error.
}
```

Write that and the machine is closed; the types above guarantee that whatever you *don't* list is unreachable.

## What this reaches, and what it still leaves open

- **Control** — impossible states (a past_due with a cancel reason won't compile), swapped IDs, unhandled new statuses, out-of-range retry counts, voluntary/reason disagreement.
- **Control at the boundary** — malformed webhook or DB rows, via the zod discriminated union and the `CHECK`.
- **Left possible, consciously**: TypeScript can't do typestate across a persistence round-trip, so `transition` returning an error value is the enforcement point — if someone writes raw SQL, only the `CHECK` catches them, and a `CHECK` cannot see the *previous* state (that needs a trigger or a transitions table). Also: dates are `Date`, so nothing stops you passing a wrong-but-valid instant, and I left `renewsAt` off `past_due` — say the word if a past_due sub needs to remember its renewal date and I'll add it.

Want me to write this into files? Give me the path and I'll lay out `ids.ts` / `subscription.ts` / the transition test, or I can fill in the transition table myself if you'd rather answer the three questions in prose.