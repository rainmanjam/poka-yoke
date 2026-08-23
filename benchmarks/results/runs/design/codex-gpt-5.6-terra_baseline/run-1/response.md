Use a discriminated union keyed by `status`:

```ts
type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;

type SubscriptionBase = {
  id: string;
  customerId: string;
  createdAt: Date;
};

type TrialingSubscription = SubscriptionBase & {
  status: "trialing";
  trialEndsAt: Date;
};

type ActiveSubscription = SubscriptionBase & {
  status: "active";
  renewsAt: Date;
};

type PastDueSubscription = SubscriptionBase & {
  status: "past_due";
  retryCount: number;
  gracePeriodEndsAt: Date;
};

type CanceledSubscription = SubscriptionBase & {
  status: "canceled";
  cancelReason: string;
  voluntarilyCanceled: boolean;
};
```

TypeScript then narrows correctly:

```ts
function nextBillingDate(sub: Subscription) {
  switch (sub.status) {
    case "trialing":
      return sub.trialEndsAt;
    case "active":
      return sub.renewsAt;
    case "past_due":
      return sub.gracePeriodEndsAt;
    case "canceled":
      return null;
  }
}
```

This prevents invalid combinations such as an active subscription having a retry count or a canceled one missing its cancellation details.