Ran the misuse enumeration first — that's what picks the shape.

**What can go wrong with the naive `{status, trialEndsAt?, retryCount?, cancelReason?, wasVoluntary?, renewsAt?}`:**

1. Six optionals claim 2⁶ = 64 states. Four are real. It permits *"active with a cancel reason"*, *"canceled with a retry count"*, *"trialing and voluntary"*.
2. `sub.trialEndsAt > now` on an active sub is `undefined > now` → `false`, silently. No error, wrong billing.
3. `wasVoluntary: boolean` and `cancelReason: string` are independent fields, so *"voluntary, reason: payment_failed"* typechecks.
4. Add `paused` or `unpaid` next year → every `if (status === ...)` chain silently falls through.
5. `subscriptionId`, `customerId`, `planId` are all `string` — adjacent same-typed params, the #1 swap footgun.

## The types

```ts
// ---------- Contact rung: branded ids, so they can't be swapped ----------
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId     = Brand<string, "CustomerId">;
export type PlanId         = Brand<string, "PlanId">;

// ---------- Cancellation: kill the boolean, correlate reason with volition ----------
export type Cancellation =
  | { kind: "voluntary";   reason: "too_expensive" | "missing_features"
                                 | "switched_provider" | "no_longer_needed" | "other"
                                 ; note?: string }
  | { kind: "involuntary"; reason: "payment_failed" | "fraud" | "terms_violation" };

// ---------- The union ----------
type SubscriptionBase = {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
  readonly planId: PlanId;
};

export type Subscription = SubscriptionBase & (
  | { status: "trialing"; trialEndsAt: Date; hasPaymentMethod: boolean }
  | { status: "active";   renewsAt: Date }
  | { status: "past_due"; retryCount: number; gracePeriodEndsAt: Date; lastFailureAt: Date }
  | { status: "canceled"; canceledAt: Date; cancellation: Cancellation; accessEndsAt: Date }
);
```

`sub.retryCount` now does not *exist* until you've narrowed to `past_due`. The check can't be forgotten because the compiler asks for it.

★ Insight ─────────────────────────────────────
`wasVoluntary` folded into the `Cancellation` discriminant is the highest-leverage move here. A `boolean` next to a `reason` string is two independent fields modelling one fact — so they can disagree. Nesting them makes "voluntary + payment_failed" unspellable, and `sub.cancellation.kind === "voluntary"` reads better than the flag ever did.
`accessEndsAt` on `canceled` is deliberate: cancel-at-period-end is the common case, and teams that omit it end up re-deriving "is this person still entitled?" from a nullable date in six places.
─────────────────────────────────────────────────

## The exhaustiveness device

One line per switch, and it's what breaks the build when you add `paused`:

```ts
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

export function hasAccess(sub: Subscription, now: Date): boolean {
  switch (sub.status) {
    case "trialing": return sub.trialEndsAt > now;
    case "active":   return true;
    case "past_due": return sub.gracePeriodEndsAt > now;
    case "canceled": return sub.accessEndsAt > now;
    default:         return assertNever(sub);
  }
}
```

Turn on `@typescript-eslint/switch-exhaustiveness-check` as `error` so you get this repo-wide without relying on anyone remembering `assertNever`.

## Parse at the boundary

Types vanish at runtime, so the DB row and the Stripe webhook both need a real parse. Zod mirrors the union directly:

```ts
const SubscriptionSchema = z.discriminatedUnion("status", [
  z.object({ status: z.literal("trialing"), trialEndsAt: z.coerce.date(),
             hasPaymentMethod: z.boolean(), /* …base… */ }),
  z.object({ status: z.literal("active"),   renewsAt: z.coerce.date(), /* … */ }),
  z.object({ status: z.literal("past_due"), retryCount: z.number().int().min(0).max(8),
             gracePeriodEndsAt: z.coerce.date(), lastFailureAt: z.coerce.date(), /* … */ }),
  z.object({ status: z.literal("canceled"), canceledAt: z.coerce.date(),
             accessEndsAt: z.coerce.date(),
             cancellation: z.discriminatedUnion("kind", [/* … */]), /* … */ }),
]);
```

Back it at the data layer with `CHECK` constraints — `status = 'past_due' OR retry_count IS NULL` and friends. That's the one rung that holds when someone runs a migration script or `psql`.

---

## One decision I shouldn't make for you

The union above prevents *illegal shapes* but not *illegal transitions* — nothing stops `{status: "canceled"} → {status: "trialing"}`. The fix is making the union's constructor private and routing every change through a transition function. But the legal edges are a business decision, not a typing one, and getting them wrong is worse than not having them.

Here's the prepared stub:

```ts
/**
 * The only legal state changes. Anything not listed here is rejected at runtime
 * and — via the mapped type below — unspellable at compile time.
 *
 * Questions only you can answer:
 *   - past_due → trialing: ever? (re-trial as a retention play?)
 *   - canceled → active: is reactivation a transition, or a brand-new subscription row?
 *   - trialing → past_due: does a trial with a card that fails go here, or straight to canceled?
 *   - active → trialing: does a plan change into a trialing tier exist?
 */
type LegalTransitions = {
  // TODO: fill in — readonly arrays of the statuses each state may move to
  trialing: readonly Subscription["status"][];
  active:   readonly Subscription["status"][];
  past_due: readonly Subscription["status"][];
  canceled: readonly Subscription["status"][];
};
```

Fill in those four lines and I'll wire up the `transition()` function that enforces them, plus the near-miss tests that prove the guard actually fails when you feed it an illegal edge.

**Left possible on purpose:** `retryCount` is a plain bounded `number` rather than a branded type (a newtype there costs more than the bug it prevents); clock/timezone handling is out of scope — every `Date` above assumes you pass `now` in rather than calling `Date.now()` inside, which is also what makes these testable.

Want me to write this into your SaaS repo? Point me at the path — I kept it inline since we're still shaping it, and this repo isn't the right home for it.