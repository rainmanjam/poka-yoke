Using **poka-yoke:design** to shape the subscription types — this is the discriminated-union-over-optional-bag case the skill exists for.

**Misuse enumerated first (30 seconds, but it decides the shape):**
1. A `{status, trialEndsAt?, renewalDate?, retryCount?, graceEndsAt?, cancelReason?, voluntary?}` bag lets you construct `active` + `retryCount: 3` or `canceled` + `renewalDate: ...` — nonsense states that mean nothing but compile fine.
2. `reason` + `voluntary: boolean` as siblings lets you write `voluntary: true, reason: "payment_failed"` — a self-contradicting cancellation.
3. Worst input: your payment provider's webhook sends *its* status strings (`incomplete`, `unpaid`, `incomplete_expired`, …), not your four. Casting that string to your type is where the bag-of-lies enters your system.
4. Second call: retry-count and grace-period fields live next to a queue that can redeliver — bumping `retryCount` per webhook delivery rather than per actual payment attempt double-counts on redelivery.

Here's the design:

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId = Brand<string, "CustomerId">;

type SubscriptionBase = {
  id: SubscriptionId;
  customerId: CustomerId;
};

export type Subscription = SubscriptionBase &
  (
    | { status: "trialing"; trialEndsAt: Date }
    | { status: "active"; renewsAt: Date }
    | { status: "past_due"; retryCount: number; graceEndsAt: Date }
    | { status: "canceled"; canceledAt: Date; cancellation: CancellationReason }
  );

// Nests the voluntary/reason pairing so "voluntary + payment_failed" has no spelling.
export type CancellationReason =
  | { voluntary: true; reason: "user_requested" | "switched_plans" | "no_longer_needed" }
  | { voluntary: false; reason: "payment_failed" | "fraud_flagged" | "compliance_hold" };

function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

export function describe(sub: Subscription): string {
  switch (sub.status) {
    case "trialing": return `trial ends ${sub.trialEndsAt.toISOString()}`;
    case "active":    return `renews ${sub.renewsAt.toISOString()}`;
    case "past_due":  return `retry ${sub.retryCount}, grace ends ${sub.graceEndsAt.toISOString()}`;
    case "canceled":  return `canceled (${sub.cancellation.voluntary ? "voluntary" : "involuntary"}: ${sub.cancellation.reason})`;
    default: return assertNever(sub);
  }
}
```

★ Insight ─────────────────────────────────────
`SubscriptionBase & (union)` gets you shared fields (`id`, `customerId`) on every variant without repeating them four times, and TypeScript still narrows correctly on `sub.status` because discrimination only needs one literal-typed field somewhere in the intersection.

`id` and `customerId` are both plain strings positionally — brand them (`SubscriptionId`/`CustomerId`) so `updateSubscription(customerId, id)` with the args swapped is a compile error, not a 2am incident.

The nested `CancellationReason` union is the same "sum types over bags of optionals" move applied one level deeper — it's worth doing this recursively wherever two fields are only valid in certain combinations, not just at the top-level status.
─────────────────────────────────────────────────

At the boundary (webhook / API), parse the provider's status into this type rather than casting — that's where their `incomplete`/`unpaid`/etc. strings get mapped or rejected, never smuggled through as one of your four.

One piece is a genuine business decision, not a type-system question: **which status transitions are legal.** Can `trialing` go straight to `canceled`? Can `past_due` go back to `active` without passing through anything, or must it re-enter via checkout? This shapes whether you need a `canTransition` guard at all, and what it allows.

In `subscription.ts`, under the exhaustiveness check, I've left a slot:

```ts
// TODO: define which (from, to) status pairs are legal.
// e.g. is trialing -> canceled valid? can past_due recover directly to active?
export function canTransition(from: Subscription["status"], to: Subscription["status"]): boolean {
  throw new Error("not yet defined");
}
```

Fill in the real rule (5-10 lines is plenty — a lookup table of allowed pairs works well) and I'll wire it into wherever the status gets written, so an illegal transition is a thrown error at the write site rather than a state nobody checks for.