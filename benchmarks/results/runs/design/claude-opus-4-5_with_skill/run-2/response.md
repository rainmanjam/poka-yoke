Now I'll apply the poka-yoke design method. First, enumerate the misuse scenarios:

`★ Insight ─────────────────────────────────────`
**The bag-of-optionals trap**: A flat type like `{status: string, trialEnd?: Date, retryCount?: number, cancelReason?: string, ...}` claims 2^5 = 32 states are legal. You described exactly 4. The other 28 are bugs waiting to happen — "active subscription with a cancel reason," "trialing with a retry count."
`─────────────────────────────────────────────────`

## Misuse Enumeration

| # | Hazard | What happens |
|---|--------|--------------|
| 1 | Access `trialEndDate` on a canceled subscription | Runtime undefined or stale data |
| 2 | Access `cancelReason` on an active subscription | Nonsense value or undefined |
| 3 | Forget to handle a new status next year | Silent fallthrough, wrong behavior |
| 4 | Mix up `trialEndDate` and `gracePeriodEnd` (both are dates) | Wrong date used, billing errors |
| 5 | Set `wasVoluntary` on a non-canceled subscription | Meaningless state |

## The Design: Discriminated Union

```typescript
// Each status is a distinct variant — no optional bags
type Subscription =
  | { status: "trialing";  trialEndDate: Date }
  | { status: "active";    renewalDate: Date }
  | { status: "past_due";  retryCount: number; gracePeriodEnd: Date }
  | { status: "canceled";  cancelReason: string; wasVoluntary: boolean };
```

**What this prevents (Control rung):**
- You cannot access `trialEndDate` without first narrowing to `status === "trialing"` — the compiler demands it
- You cannot construct a subscription with mismatched fields — `{ status: "active", cancelReason: "..." }` won't typecheck
- Adding a fifth status (`"paused"`) breaks every `switch` that doesn't handle it (with the exhaustiveness check below)

## Exhaustive Handling

```typescript
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

function getNextBillingAction(sub: Subscription): string {
  switch (sub.status) {
    case "trialing":
      return `Trial ends ${sub.trialEndDate.toISOString()}`;
    case "active":
      return `Renews ${sub.renewalDate.toISOString()}`;
    case "past_due":
      return `Retry #${sub.retryCount}, grace ends ${sub.gracePeriodEnd.toISOString()}`;
    case "canceled":
      return `Canceled (${sub.wasVoluntary ? "voluntary" : "involuntary"}): ${sub.cancelReason}`;
    default:
      return assertNever(sub);
  }
}
```

## Optional Refinements

**If cancel reasons are enumerated** (not free-form):

```typescript
type CancelReason = 
  | "user_requested" 
  | "payment_failed" 
  | "fraud" 
  | "expired";

// Then in the canceled variant:
| { status: "canceled"; cancelReason: CancelReason; wasVoluntary: boolean }
```

**If you want branded dates** to prevent swapping `trialEndDate` and `gracePeriodEnd`:

```typescript
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

type TrialEndDate = Brand<Date, "TrialEndDate">;
type GracePeriodEnd = Brand<Date, "GracePeriodEnd">;
type RenewalDate = Brand<Date, "RenewalDate">;
```

This is heavier — worth it if you're passing these dates between functions where a swap is plausible; overkill if they only live inside the union.

## What This Leaves Possible

- **Runtime violations from untyped boundaries.** If subscriptions come from an API or database, you need a parse step (Zod schema) at that boundary.
- **Business logic errors** like setting `retryCount: -1`. Add `z.number().nonnegative()` if that matters.

Want me to write the Zod parse schema for the API boundary, or is the type definition enough for now?