This is a textbook case for a **discriminated union** — each status carries different data, and the compiler should enforce you handle each correctly.

`★ Insight ─────────────────────────────────────`
A flat type with optional fields (`trialEndDate?: Date, cancelReason?: string, ...`) compiles but fails at runtime — nothing stops you from reading `trialEndDate` on a canceled subscription. Discriminated unions make illegal states unrepresentable.
`─────────────────────────────────────────────────`

```typescript
// subscriptions/types.ts

type TrialingSubscription = {
  status: "trialing";
  trialEndDate: Date;
};

type ActiveSubscription = {
  status: "active";
  renewalDate: Date;
};

type PastDueSubscription = {
  status: "past_due";
  retryCount: number;
  gracePeriodEnd: Date;
};

type CanceledSubscription = {
  status: "canceled";
  cancelReason: string;
  voluntary: boolean;
};

type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;
```

Usage — the compiler narrows automatically:

```typescript
function handleSubscription(sub: Subscription) {
  switch (sub.status) {
    case "trialing":
      // sub.trialEndDate is available, sub.cancelReason is a type error
      console.log(`Trial ends ${sub.trialEndDate}`);
      break;
    case "past_due":
      // sub.retryCount and sub.gracePeriodEnd available here
      break;
    // If you forget a case, TypeScript warns (with exhaustiveness check)
  }
}
```

**One design question for you**: Should `cancelReason` be a free-form string, or an enum of known reasons (`"payment_failed" | "user_requested" | "fraud" | ...`)? An enum prevents typos and lets you build UI around known values — but limits flexibility if reasons evolve. What fits your domain?