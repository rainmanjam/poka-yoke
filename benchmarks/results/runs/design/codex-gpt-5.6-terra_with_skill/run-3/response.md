Use a discriminated union—each status carries exactly the fields that are valid for it.

```ts
declare const brand: unique symbol;
type Brand<T, Name extends string> = T & {
  readonly [brand]: Name;
};

export type Instant = Brand<string, "UtcIso8601Instant">;
export type RetryCount = Brand<number, "NonNegativeInteger">;

type SubscriptionCore = {
  id: Brand<string, "SubscriptionId">;
  customerId: Brand<string, "CustomerId">;
};

export type Subscription =
  | (SubscriptionCore & {
      status: "trialing";
      trialEndsAt: Instant;
    })
  | (SubscriptionCore & {
      status: "active";
      renewsAt: Instant;
    })
  | (SubscriptionCore & {
      status: "past_due";
      retryCount: RetryCount;
      gracePeriodEndsAt: Instant;
    })
  | (SubscriptionCore & {
      status: "canceled";
      cancelReason: string;
      isVoluntary: boolean;
    });
```

This makes these mistakes impossible at compile time (Control rung):

- A `trialing` subscription without a trial-end date.
- A canceled subscription carrying retry/grace-period fields.
- An active subscription accidentally treated as if it had a cancellation reason.
- A status typo.

Narrow on `status`, and use exhaustive handling when behavior differs:

```ts
function nextBillingEvent(subscription: Subscription): Instant | null {
  switch (subscription.status) {
    case "trialing":
      return subscription.trialEndsAt;
    case "active":
      return subscription.renewsAt;
    case "past_due":
      return subscription.gracePeriodEndsAt;
    case "canceled":
      return null;
  }
}
```

Parse `Instant` and `RetryCount` at your API/database boundary—e.g. require UTC ISO-8601 timestamps and non-negative integers—rather than letting arbitrary strings and numbers enter this union. With `strict`, `exactOptionalPropertyTypes`, and exhaustive-switch checking enabled, adding a future status such as `"paused"` will force every relevant handler to be updated.