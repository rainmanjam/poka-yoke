Using the poka-yoke router → **`design`** mode (new interface, "what should the types look like"), with `references/lang-typescript.md` and the hazard catalog.

## Misuse I enumerated first

- **C8 bag-of-optionals** — `{ status, trialEndsAt?, retryCount?, cancelReason?, voluntary? }` claims 2⁵ legal states for the 4 that exist. It lets you build an `active` sub carrying a cancel reason.
- **C2 boolean flag** — `voluntary: boolean` sits next to `cancelReason`, so "voluntary + payment_failed" is spellable. Those two fields are one decision, not two.
- **M3 illegal transitions** — `sub.status = "active"` assigned from a webhook handler, an admin tool, and a cron job means all three must know the state machine. One won't.
- **F1 exhaustiveness** — when `paused` ships next year, the right answer is "the build breaks."
- **C1 stale carry-over** — a transition built with `{...sub, status: "active"}` leaves `trialEndsAt` attached forever.
- **M2 at-least-once** — Stripe delivers webhooks more than once; transitions must be keyed.

`★ Insight ─────────────────────────────────────`
The single highest-leverage move here isn't the union itself — it's that **the event carries the new variant's required fields**. `transitionTo(sub, "active")` forces the caller to remember a renewal date; `apply(sub, { type: "payment_succeeded", renewsAt })` makes forgetting it a compile error.
`─────────────────────────────────────────────────`

```ts
// src/billing/subscription.ts

// ── Contact: ids that cannot be swapped ────────────────────────────────
declare const brand: unique symbol;
type Brand<T, B extends string> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId     = Brand<string, "CustomerId">;
export type PlanId         = Brand<string, "PlanId">;

export const MAX_DUNNING_RETRIES = 8;
export type RetryCount = Brand<number, "RetryCount">;
export const RetryCount = (n: number): RetryCount => {
  if (!Number.isInteger(n) || n < 0 || n > MAX_DUNNING_RETRIES)
    throw new RangeError(`retryCount must be an integer 0..${MAX_DUNNING_RETRIES}, got ${n}`);
  return n as RetryCount;
};

// ── Contact: why it ended is one decision, not a flag plus a string ────
export type Cancellation =
  | { readonly kind: "voluntary";   readonly reason: VoluntaryReason; readonly note?: string }
  | { readonly kind: "involuntary"; readonly reason: InvoluntaryReason };

export type VoluntaryReason =
  | "too_expensive" | "missing_features" | "switched_provider" | "no_longer_needed" | "other";
export type InvoluntaryReason =
  | "dunning_exhausted" | "fraud" | "terms_violation";

// ── The union: exactly four shapes, no optional fields ────────────────
export type SubscriptionState =
  | { readonly status: "trialing"; readonly trialEndsAt: Date }
  | { readonly status: "active";   readonly renewsAt: Date }
  | { readonly status: "past_due"; readonly retryCount: RetryCount;
                                   readonly gracePeriodEndsAt: Date }
  | { readonly status: "canceled"; readonly canceledAt: Date;
                                   readonly cancellation: Cancellation };

export type Status = SubscriptionState["status"];

export type SubscriptionIdentity = {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
  readonly planId: PlanId;
};

export type Subscription = SubscriptionIdentity & SubscriptionState;

// ── Motion-step: events carry what the destination state requires ─────
export type SubscriptionEvent =
  | { readonly type: "trial_converted";   readonly at: Date; readonly renewsAt: Date }
  | { readonly type: "payment_succeeded"; readonly at: Date; readonly renewsAt: Date }
  | { readonly type: "payment_failed";    readonly at: Date;
      readonly retryCount: RetryCount; readonly gracePeriodEndsAt: Date }
  | { readonly type: "canceled";          readonly at: Date;
      readonly cancellation: Cancellation };

export type IllegalTransition = {
  readonly kind: "illegal_transition";
  readonly from: Status;
  readonly event: SubscriptionEvent["type"];
};

export type TransitionResult =
  | { readonly ok: true;  readonly subscription: Subscription }
  | { readonly ok: false; readonly error: IllegalTransition };

// ──────────────────────────────────────────────────────────────────────
// TODO(you): the legal transition table. See the request below.
// Record<Status, ...> means adding a fifth status breaks the build here.
// ──────────────────────────────────────────────────────────────────────
const LEGAL: Readonly<Record<Status, readonly SubscriptionEvent["type"][]>> = {
  trialing: [],
  active:   [],
  past_due: [],
  canceled: [],
};

function assertNever(x: never): never {
  throw new Error(`Unhandled variant: ${JSON.stringify(x)}`);
}

/** The ONLY way to reach a new state. Nothing else assigns `status`. */
export function apply(sub: Subscription, event: SubscriptionEvent): TransitionResult {
  if (!LEGAL[sub.status].includes(event.type))
    return { ok: false, error: { kind: "illegal_transition", from: sub.status, event: event.type } };

  // Rebuild from identity only — no stale trialEndsAt riding along.
  const base: SubscriptionIdentity =
    { id: sub.id, customerId: sub.customerId, planId: sub.planId };

  switch (event.type) {
    case "trial_converted":
    case "payment_succeeded":
      return { ok: true, subscription: { ...base, status: "active", renewsAt: event.renewsAt } };
    case "payment_failed":
      return { ok: true, subscription: { ...base, status: "past_due",
        retryCount: event.retryCount, gracePeriodEndsAt: event.gracePeriodEndsAt } };
    case "canceled":
      return { ok: true, subscription: { ...base, status: "canceled",
        canceledAt: event.at, cancellation: event.cancellation } };
    default:
      return assertNever(event);
  }
}
```

**Boundary (parse, don't validate)** — the webhook payload is not a `Subscription` until it has been parsed:

```ts
const Identity = z.object({
  id: z.string().min(1).brand<"SubscriptionId">(),
  customerId: z.string().min(1).brand<"CustomerId">(),
  planId: z.string().min(1).brand<"PlanId">(),
});
export const SubscriptionSchema = z.discriminatedUnion("status", [
  Identity.extend({ status: z.literal("trialing"), trialEndsAt: z.coerce.date() }),
  Identity.extend({ status: z.literal("active"),   renewsAt: z.coerce.date() }),
  Identity.extend({ status: z.literal("past_due"),
    retryCount: z.number().int().min(0).max(MAX_DUNNING_RETRIES).brand<"RetryCount">(),
    gracePeriodEndsAt: z.coerce.date() }),
  Identity.extend({ status: z.literal("canceled"), canceledAt: z.coerce.date(),
    cancellation: CancellationSchema }),
]).strict();
```

**The durable half — the database.** TS types evaporate at runtime; a psql session or a second service does not see them:

```sql
CONSTRAINT fields_match_status CHECK (
  CASE status
    WHEN 'trialing' THEN trial_ends_at IS NOT NULL AND renews_at IS NULL
                     AND retry_count IS NULL AND canceled_at IS NULL
    WHEN 'active'   THEN renews_at IS NOT NULL AND retry_count IS NULL AND canceled_at IS NULL
    WHEN 'past_due' THEN retry_count IS NOT NULL AND grace_period_ends_at IS NOT NULL
                     AND canceled_at IS NULL
    WHEN 'canceled' THEN canceled_at IS NOT NULL AND cancel_kind IS NOT NULL
                     AND cancel_reason IS NOT NULL
  END
),
CONSTRAINT retry_count_bounded CHECK (retry_count IS NULL OR retry_count BETWEEN 0 AND 8)
```

A row-level `CHECK` can't see where the row came *from*, so it cannot police `canceled → active`. For that, write every change to a `subscription_transitions` table with `(from_status, to_status)` foreign-keyed into a legal-pairs table, and put `UNIQUE (provider_event_id)` on it — that same index is your webhook idempotency device.

## Rungs reached, and what I left possible

| Hazard | Device | Rung |
|---|---|---|
| Nonsense field combinations | discriminated union | **Control** |
| `voluntary` + wrong reason | nested `Cancellation` union | **Control** |
| Forgetting `renewsAt` on activation | event carries the payload | **Control** |
| New status silently unhandled | `Record<Status, …>` + `assertNever` | **Control** |
| Illegal transition | `apply()` returns an error | **Warning** — true typestate would need a distinct type per state and would infect every repository signature; not worth it for four states |
| Corrupt rows from outside the app | `CHECK` constraints | **Control** |

Left possible on purpose: `Date` is still `Date` (inject a clock rather than calling `new Date()` inside billing logic); nothing stops code reading `sub.status` and branching by hand instead of calling `apply`; and the brand constructors use `as`, so lint `@typescript-eslint/no-unnecessary-type-assertion` plus a ban on `as unknown as T` outside this file is part of the device, not a style preference.

---

## One thing I want from you

`LEGAL` is stubbed empty on purpose — it's the only part of this that's a business decision rather than a typing one, and four questions in it have no universally right answer:

1. Does `trialing` go straight to `past_due` when the first charge fails, or to `canceled`?
2. Can `canceled` come back to `active` (reactivation), or is that always a brand-new subscription row? This is the one that bites — allowing it means every "was this customer ever churned" query gets subtly wrong.
3. Can `past_due` → `trialing` ever happen (a support-granted grace trial)?
4. Does `active` → `canceled` fire immediately, or does your cancel-at-period-end flow keep it `active` until the renewal date passes?

Fill in the table — about 6 lines:

```ts
const LEGAL: Readonly<Record<Status, readonly SubscriptionEvent["type"][]>> = {
  trialing: ["trial_converted", /* payment_failed? canceled? */],
  active:   [/* … */],
  past_due: [/* … */],
  canceled: [/* [] if terminal */],
};
```

Tell me your answers and I'll finish it, plus the paired test file — one case per legal transition that must pass, and one per illegal pair that must be rejected, which is what keeps this from being a table nobody ever proved.