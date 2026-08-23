Now I'll design your subscription types using the poka-yoke method.

## Misuse enumeration

Before writing the types, here's what could go wrong with a naive approach:

1. **Bag of optionals permits nonsense** — if all fields are optional, you could construct a "canceled subscription with a trial end date" or "active subscription with a cancel reason"
2. **Accessing wrong fields** — code reads `trialEndDate` on a canceled sub → runtime `undefined`, not compile error
3. **Forgetting required data** — a `past_due` without `gracePeriodEnd`, an `active` without `renewalDate`
4. **New status added later** — silently falls through every switch instead of breaking the build
5. **Status as plain string** — typos compile fine

---

`★ Insight ─────────────────────────────────────`
**Discriminated unions** solve all five. The `status` literal becomes a *discriminant* — TypeScript narrows the type when you check it, making `sub.trialEndDate` accessible only after you've proven `sub.status === "trialing"`. The bag-of-optionals approach claims 2^N states are valid; a union permits exactly the 4 that exist.
`─────────────────────────────────────────────────`

---

## The types

```ts
// ─── Base fields shared by all states ───
interface SubscriptionBase {
  id: string;
  customerId: string;
  planId: string;
  createdAt: Date;
}

// ─── Each state is its own variant ───
interface TrialingSub extends SubscriptionBase {
  status: "trialing";
  trialEndDate: Date;
}

interface ActiveSub extends SubscriptionBase {
  status: "active";
  renewalDate: Date;
}

interface PastDueSub extends SubscriptionBase {
  status: "past_due";
  retryCount: number;
  gracePeriodEnd: Date;
}

interface CanceledSub extends SubscriptionBase {
  status: "canceled";
  cancelReason: string;
  voluntary: boolean;
}

// ─── The union ───
type Subscription = TrialingSub | ActiveSub | PastDueSub | CanceledSub;

// ─── Exhaustiveness helper ───
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}
```

---

## Usage pattern — exhaustive switch

```ts
function getDaysUntilAction(sub: Subscription): number | null {
  switch (sub.status) {
    case "trialing":
      return daysUntil(sub.trialEndDate);   // ✓ trialEndDate exists here
    case "active":
      return daysUntil(sub.renewalDate);    // ✓ renewalDate exists here
    case "past_due":
      return daysUntil(sub.gracePeriodEnd); // ✓ gracePeriodEnd exists here
    case "canceled":
      return null;                          // ✓ no date fields to access
    default:
      return assertNever(sub);              // ← breaks build if you add a 5th status
  }
}
```

---

`★ Insight ─────────────────────────────────────`
The `assertNever(sub)` line is the **fixed-value device** — if someone adds `status: "paused"` next year, TypeScript will error because `PausedSub` isn't assignable to `never`. The mistake announces itself at compile time, not in production.
`─────────────────────────────────────────────────`

---

## What this makes impossible (Control rung)

| Misuse | Device |
|--------|--------|
| Nonsense state combinations | Union — only 4 shapes exist |
| Accessing `trialEndDate` on canceled | Narrowing — field doesn't exist on that variant |
| Missing `gracePeriodEnd` on past_due | Required field on `PastDueSub` |
| New status silently ignored | `assertNever` + exhaustive switch |
| Typo in status string | Literal types — `"actve"` won't compile |

## What's still possible (conscious tradeoff)

- **Runtime data from an API could still be malformed** — you need a Zod schema at the boundary to parse JSON into this union. The types protect code that *already has* a `Subscription`; they don't protect the parse step.
- **Business logic errors** (charging a canceled sub, extending a trial that already ended) aren't prevented by this shape — those need domain methods or state machine transitions.

Want me to add the Zod parse layer, or add helper type guards like `isActive(sub): sub is ActiveSub`?