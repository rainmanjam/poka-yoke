Here's the type design using **discriminated unions** — TypeScript's best pattern for state machines:

```typescript
/** Bounded retry count prevents infinite retry loops */
type RetryCount = 0 | 1 | 2 | 3;

interface SubscriptionBase {
  id: string;
  customerId: string;
  planId: string;
  createdAt: Date;
}

interface TrialingSubscription extends SubscriptionBase {
  status: "trialing";
  trialEndDate: Date;
}

interface ActiveSubscription extends SubscriptionBase {
  status: "active";
  renewalDate: Date;
}

interface PastDueSubscription extends SubscriptionBase {
  status: "past_due";
  retryCount: RetryCount;
  gracePeriodEnd: Date;
  renewalDate: Date;
}

interface CanceledSubscription extends SubscriptionBase {
  status: "canceled";
  canceledAt: Date;
  cancelReason: string;
  voluntary: boolean;
}

export type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;
```

`★ Insight ─────────────────────────────────────`
**Why this works:**
- **Type narrowing**: `if (sub.status === "past_due")` → TypeScript knows `sub.retryCount` exists
- **Impossible states prevented**: Can't have `cancelReason` on active subs (compile error)
- **Exhaustiveness**: Switch statements force you to handle all cases — add a 5th state later, get compile errors everywhere you forgot to handle it
`─────────────────────────────────────────────────`

**Key decisions made:**

1. **Bounded retry count** (`0 | 1 | 2 | 3`) instead of `number` — prevents runaway retry loops
2. **`voluntary` flag** on cancellation — distinguishes user cancellations from system auto-cancels (e.g., after max retries)
3. **`renewalDate` on `past_due`** — you still need to know the original billing cycle even when payment failed

**Questions for you** (affects the transition logic):
- After 3 failed retries, should it auto-transition to `canceled` with `voluntary: false`?
- Can you go directly from `trialing` → `canceled`, or must trials always become `active` first?
- Can canceled subscriptions be reactivated, or must you create a new subscription?

Want me to implement the state transition functions once you decide on those rules?