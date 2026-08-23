Use a discriminated union so each state can only carry the fields it needs:

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
  voluntary: boolean;
};
```

TypeScript then narrows safely:

```ts
function nextImportantDate(sub: Subscription) {
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

If these cross an API/database boundary, use ISO strings (`string`) there and convert them to `Date` in your application layer.