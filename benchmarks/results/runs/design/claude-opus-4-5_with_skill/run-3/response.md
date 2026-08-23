Now I'll apply the design ritual — enumerate misuses first, then design against them.

---

## Misuse enumeration

Before writing the types, here's what could go wrong:

1. **Invalid state combinations** — a "canceled" subscription with `trialEndDate`, or "active" with `cancelReason`. With optional fields, callers can construct nonsense.
2. **Accessing nonexistent properties** — reading `retryCount` on an active subscription without checking status first.
3. **Status string typos** — `"cancelled"` vs `"canceled"`, caught at runtime instead of compile time.
4. **Missing state-specific data** — a `past_due` subscription without retry info.
5. **Adding a fifth status later** — handlers silently fall through instead of breaking the build.

---

## The design

A **discriminated union** on `status` makes illegal states unrepresentable (Control rung, contact lens). Each variant carries *only* the fields that make sense for it:

```ts
// ─── Branded IDs (prevent swapping subscription/user/plan IDs) ───
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type UserId = Brand<string, "UserId">;
export type PlanId = Brand<string, "PlanId">;

// ─── Cancel reasons (exhaustive, not a loose string) ───
export type CancelReason =
  | "user_requested"
  | "payment_failed"
  | "plan_discontinued"
  | "admin_action";

// ─── The discriminated union ───
export type Subscription =
  | { status: "trialing";  id: SubscriptionId; userId: UserId; planId: PlanId; trialEndDate: Date }
  | { status: "active";    id: SubscriptionId; userId: UserId; planId: PlanId; renewalDate: Date }
  | { status: "past_due";  id: SubscriptionId; userId: UserId; planId: PlanId; retryCount: number; graceEndDate: Date }
  | { status: "canceled";  id: SubscriptionId; userId: UserId; planId: PlanId; cancelReason: CancelReason; voluntary: boolean };
```

---

`★ Insight ─────────────────────────────────────`
**Why this shape works:**
- `sub.trialEndDate` is a compile error until you've narrowed to `status === "trialing"` — the check can't be forgotten.
- Adding a 5th status (e.g., `"paused"`) will break every `switch` that uses `assertNever`, so handlers update or the build fails.
- Branded IDs mean `transfer(subscriptionId, userId)` is a type error, not a production incident.
`─────────────────────────────────────────────────`

---

## Exhaustive handler pattern

Pair with this helper so new statuses break the build:

```ts
function assertNever(x: never): never {
  throw new Error(`Unhandled status: ${JSON.stringify(x)}`);
}

function getStatusMessage(sub: Subscription): string {
  switch (sub.status) {
    case "trialing":  return `Trial ends ${sub.trialEndDate.toISOString()}`;
    case "active":    return `Renews ${sub.renewalDate.toISOString()}`;
    case "past_due":  return `Retry ${sub.retryCount}, grace ends ${sub.graceEndDate.toISOString()}`;
    case "canceled":  return `Canceled (${sub.cancelReason}, voluntary: ${sub.voluntary})`;
    default:          return assertNever(sub);
  }
}
```

---

## What's left possible (conscious tradeoffs)

| Hazard | Why left open |
|--------|---------------|
| Invalid dates (past trial end, negative retry count) | Runtime validation at parse boundary; type system can't express "future date" |
| Database storing old union shape after migration | DB schema needs `CHECK` constraints to mirror the union — see "push to data layer" |

---

**Rung achieved:** Control via discriminated union — illegal states have no spelling. Enable `@typescript-eslint/switch-exhaustiveness-check` to enforce the fixed-value lens at every handler.