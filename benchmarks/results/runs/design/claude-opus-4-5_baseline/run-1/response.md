This is a textbook case for a discriminated union — each status carries different data, and TypeScript can narrow the type based on the `status` field.

`★ Insight ─────────────────────────────────────`
**Discriminated unions** beat optional fields here because:
1. TypeScript enforces that you handle each case
2. You can't accidentally access `trialEndDate` on a canceled sub
3. Adding a new status causes compile errors everywhere it's unhandled
`─────────────────────────────────────────────────`

Here's the structure:

```typescript
// types/subscription.ts

type SubscriptionBase = {
  id: string;
  customerId: string;
  planId: string;
  createdAt: Date;
};

type TrialingSub = SubscriptionBase & {
  status: "trialing";
  trialEndDate: Date;
};

type ActiveSub = SubscriptionBase & {
  status: "active";
  renewalDate: Date;
};

type PastDueSub = SubscriptionBase & {
  status: "past_due";
  retryCount: number;
  gracePeriodEnd: Date;
};

type CanceledSub = SubscriptionBase & {
  status: "canceled";
  cancelReason: string;
  wasVoluntary: boolean;
};

export type Subscription = TrialingSub | ActiveSub | PastDueSub | CanceledSub;
```

**One design choice for you:** The `cancelReason` as a free string is flexible but error-prone. You could constrain it to known reasons:

```typescript
// In types/subscription.ts, replace cancelReason: string with:
type CancelReason = "payment_failed" | "user_requested" | "plan_discontinued" | "fraud" | "other";
```

Do you want the constrained enum approach, or keep it as a free string for flexibility? This affects how you'll validate cancel requests downstream.