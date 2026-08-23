Using **poka-yoke:design** (routed via poka-yoke.md → design mode) for this — you're specifying a new interface, so the goal is a shape where the invalid combinations (e.g. a `past_due` sub with a `cancelReason`, or an `active` sub with no `renewalDate`) can't be written down at all, not just validated against.

**Misuse enumerated first** (per the skill — decide this before the signature):

1. **Adjacent same-type fields**: `trialEndDate`, `renewalDate`, `gracePeriodEndDate` are all `Date`, `retryCount` is a bare `number` — a flat struct with all fields optional lets you set `gracePeriodEndDate` on an `active` sub or leave `renewalDate` off one.
2. **Must-remember rule**: "only read `retryCount` when `status === 'past_due'`" — today that's a comment; nothing stops a caller from reading it on a `trialing` sub and getting `undefined` silently.
3. **Nonsense states**: a flat optional-bag permits `2^n` combinations; only 4 are real. `canceled` + `retryCount`, `active` + `cancelReason` are all constructible garbage.
4. **Reason/voluntary drift**: `cancelReason` and `voluntary: boolean` are two independent fields describing one fact — nothing stops `{ voluntary: true, reason: "chargeback" }`, which is a contradiction in terms.
5. **New status next year** (e.g. `"paused"`): the failure mode you want is "the build breaks everywhere status is handled," not "silently falls through the default case."

Design, addressing each:

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId = Brand<string, "CustomerId">;

interface SubscriptionBase {
  id: SubscriptionId;
  customerId: CustomerId;
}

export type Subscription =
  | (SubscriptionBase & {
      status: "trialing";
      trialEndDate: Date;
    })
  | (SubscriptionBase & {
      status: "active";
      renewalDate: Date;
    })
  | (SubscriptionBase & {
      status: "past_due";
      retryCount: number;
      gracePeriodEndDate: Date;
    })
  | (SubscriptionBase & {
      status: "canceled";
      cancellation: Cancellation;
    });

// Couples the reason vocabulary to voluntary/involuntary so they can't drift —
// "chargeback" as a voluntary reason has no spelling.
export type Cancellation =
  | { voluntary: true; reason: VoluntaryCancelReason }
  | { voluntary: false; reason: InvoluntaryCancelReason };

export type VoluntaryCancelReason =
  | "too_expensive"
  | "missing_features"
  | "switched_competitor"
  | "no_longer_needed"
  | "other";

export type InvoluntaryCancelReason =
  | "payment_failed_final"
  | "fraud"
  | "chargeback";

function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

export function describeStatus(sub: Subscription): string {
  switch (sub.status) {
    case "trialing":
      return `trial ends ${sub.trialEndDate.toISOString()}`;
    case "active":
      return `renews ${sub.renewalDate.toISOString()}`;
    case "past_due":
      return `retry ${sub.retryCount}, grace ends ${sub.gracePeriodEndDate.toISOString()}`;
    case "canceled":
      return sub.cancellation.voluntary
        ? `canceled voluntarily: ${sub.cancellation.reason}`
        : `canceled involuntarily: ${sub.cancellation.reason}`;
    default:
      return assertNever(sub);
  }
}
```

★ Insight ─────────────────────────────────────
`SubscriptionBase & { status: "active"; renewalDate: Date }` — intersecting the shared shape into each arm, rather than one interface with a `status` field plus everything optional, is what makes `sub.retryCount` a compile error until TypeScript has narrowed `sub.status === "past_due"`. That narrowing is *why* discriminated unions beat optional bags: the compiler forces the check at every read site, not just at construction.

The nested `Cancellation` union is doing the same trick one level down — it's a discriminated union whose discriminant (`voluntary`) is a `boolean` instead of a string literal, which TypeScript narrows just as well.
─────────────────────────────────────────────────

**Rungs reached**: Control via discriminated union (illegal field combinations have no spelling) and Control via `assertNever` (a fifth status added later fails the build at every switch, rather than falling through). `SubscriptionId`/`CustomerId` are branded so a `CustomerId` can't be passed where a `SubscriptionId` is expected — cheap insurance since they're adjacent-`string` params in most lookup functions.

**Left alone deliberately**: `retryCount` is a plain `number`, not a branded `NonNegativeInt` — the blast radius of a stray negative retry count is low and a newtype there is the kind of thing the skill calls out as going too far. I also didn't validate that `trialEndDate`/`renewalDate`/`gracePeriodEndDate` are actually in the future — that's a runtime invariant, not a type-level one, and belongs at the boundary where the subscription is constructed (webhook handler, DB row mapper), not in the type itself.

One piece I'm deliberately leaving to you: **which status transitions are legal**. That's billing policy I don't know — can `past_due` go straight back to `active`, or must it round-trip through a webhook confirmation? Can `trialing` cancel directly, or does it have to become `active` first? Getting this wrong either lets illegal jumps through silently or blocks a legitimate Stripe webhook sequence.

```ts
// TODO: fill in the transition matrix per your billing policy.
// Returning false should be a Control-rung block at the call site — throw, don't warn.
function isLegalTransition(from: Subscription["status"], to: Subscription["status"]): boolean {
  // e.g. return from === "trialing" && (to === "active" || to === "canceled");
}
```

That's a 5-10 line call only you can make — want to sketch the allowed transitions, or tell me your billing provider's webhook sequence and I'll derive it?