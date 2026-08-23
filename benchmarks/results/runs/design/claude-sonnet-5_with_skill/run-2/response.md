Using the poka-yoke `design` skill to shape these types — since you're writing this from scratch, the misuse-enumeration happens before the signature.

**Misuses worth designing out here:**
1. `SubscriptionId`, `CustomerId`, `PlanId` are structurally identical strings — swappable at any call site with no type error.
2. A bag-of-optionals shape (`trialEndDate?`, `retryCount?`, `gracePeriodEndDate?`, `cancelReason?`, `voluntary?`, `renewalDate?` all on one object) permits nonsense combinations — a `canceled` sub with a `retryCount`, an `active` sub with a `cancelReason`. With 6 optional fields you're claiming 2^6 states are legal when exactly 4 are.
3. Nothing stops a caller reading `.trialEndDate` off a subscription that's actually `past_due` — it'd just be `undefined` at runtime, silently.
4. When you add a 5th status next year (`paused`?), you want every `switch` that handles status to fail to compile until it's handled — not to silently fall through the default case.

**The design — discriminated union keyed on `status`, branded IDs so they can't swap:**

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId = Brand<string, "CustomerId">;
export type PlanId = Brand<string, "PlanId">;

interface SubscriptionBase {
  id: SubscriptionId;
  customerId: CustomerId;
  planId: PlanId;
}

type Cancellation =
  | { voluntary: true; reason: "user_requested" | "switched_provider" | "no_longer_needed" }
  | { voluntary: false; reason: "payment_failed" | "fraud_flagged" | "chargeback" };

export type Subscription =
  | (SubscriptionBase & { status: "trialing"; trialEndDate: Date })
  | (SubscriptionBase & { status: "active"; renewalDate: Date })
  | (SubscriptionBase & { status: "past_due"; retryCount: number; gracePeriodEndDate: Date })
  | (SubscriptionBase & ({ status: "canceled" } & Cancellation));
```

`Cancellation` is its own nested union rather than `{ cancelReason: string; voluntary: boolean }` — a free-text reason next to a boolean lets someone pass `reason: "fraud_flagged", voluntary: true`, which is a lie the type shouldn't allow. Narrowing on `voluntary` narrows which reasons are even sayable.

**Exhaustiveness — the part that pays off when status #5 arrives:**

```ts
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

function describe(sub: Subscription): string {
  switch (sub.status) {
    case "trialing": return `trial ends ${sub.trialEndDate.toISOString()}`;
    case "active":    return `renews ${sub.renewalDate.toISOString()}`;
    case "past_due":  return `retry ${sub.retryCount}, grace ends ${sub.gracePeriodEndDate.toISOString()}`;
    case "canceled":  return sub.voluntary ? `left: ${sub.reason}` : `lost: ${sub.reason}`;
    default:          return assertNever(sub);
  }
}
```

Add a `paused` variant to the union and this function stops compiling until you handle it — that's `@typescript-eslint/switch-exhaustiveness-check` doing its job repo-wide, not just here.

★ Insight ─────────────────────────────────────
The nested `Cancellation` union is the same move twice at two altitudes: once splitting `Subscription` by `status`, once splitting the `canceled` case by `voluntary`. Whenever two fields are correlated (a boolean gating which enum values are legal), that's a signal to nest a union rather than flatten to siblings — flattening is exactly how you get back to the bag-of-optionals problem one level down.

Branding costs nothing at runtime (it's erased at compile time) — it only protects you inside this codebase. If subscription IDs ever cross a network boundary (an API request body, a queue message), you need a *parse* at that edge (Zod's `.brand()`) — the compile-time brand alone won't stop `"cus_123"` being sent where a `SubscriptionId` is expected over HTTP.
─────────────────────────────────────────────────

**What this doesn't cover — and needs your call:** which transitions between these four states are actually legal (`canceled` is presumably terminal; can `past_due` go straight back to `active` or must it re-enter `trialing`?). That's a billing-policy decision, not a type-system one, and it shapes whether you want a typestate/transition-guard function on top of this union. If you want that next, sketch the legal-transition table in `isValidTransition(from: Subscription["status"], to: Subscription["status"]): boolean` — you know your dunning/grace-period policy, I don't, and getting it wrong silently is worse than a stub.