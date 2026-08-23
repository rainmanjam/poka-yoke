Use a discriminated union so each status permits only its relevant fields:

```ts
type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;

type SubscriptionBase = {
  id: string;
  customerId: string;
  planId: string;
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

TypeScript narrows correctly based on `status`:

```ts
function getNextAction(sub: Subscription) {
  switch (sub.status) {
    case "trialing":
      return `Trial ends ${sub.trialEndsAt}`;

    case "active":
      return `Renews ${sub.renewsAt}`;

    case "past_due":
      return `Retry #${sub.retryCount} before ${sub.gracePeriodEndsAt}`;

    case "canceled":
      return sub.voluntarilyCanceled
        ? `Canceled by customer: ${sub.cancelReason}`
        : `Canceled: ${sub.cancelReason}`;
  }
}
```

For API/database boundaries, consider using ISO strings (`string`) instead of `Date`, then parse them at the edge of your application.