Use a discriminated union—not one object with optional fields:

```ts
type Subscription =
  | {
      status: "trialing";
      trialEndsAt: UtcInstant;
    }
  | {
      status: "active";
      renewsAt: UtcInstant;
    }
  | {
      status: "past_due";
      retryCount: RetryCount;
      gracePeriodEndsAt: UtcInstant;
    }
  | {
      status: "canceled";
      cancellation: {
        kind: "voluntary" | "involuntary";
        reason: CancelReason;
      };
    };

declare const brand: unique symbol;
type Brand<T, Name extends string> = T & {
  readonly [brand]: Name;
};

type UtcInstant = Brand<string, "UtcInstant">; // parsed ISO-8601 UTC timestamp
type RetryCount = Brand<number, "RetryCount">; // parsed non-negative integer
type CancelReason = Brand<string, "CancelReason">; // parsed non-empty value
```

This is Control-rung mistake-proofing: a trial cannot accidentally carry retry data, and a canceled subscription cannot omit its cancellation details. Model “voluntary” as a literal union rather than a boolean so it remains readable and exhaustive if more cancellation modes are added later.

Parse and brand `UtcInstant`, `RetryCount`, and `CancelReason` at your API/database boundary; don’t let arbitrary `string` and `number` values flow into the domain model. Also make downstream handling exhaustive:

```ts
function assertNever(value: never): never {
  throw new Error(`Unhandled subscription: ${JSON.stringify(value)}`);
}

function nextBillingDate(sub: Subscription): UtcInstant | null {
  switch (sub.status) {
    case "trialing":
      return sub.trialEndsAt;
    case "active":
      return sub.renewsAt;
    case "past_due":
      return sub.gracePeriodEndsAt;
    case "canceled":
      return null;
    default:
      return assertNever(sub);
  }
}
```

The remaining concern is transitions—e.g. whether `canceled → active` is allowed. Put those behind a single transition function or state machine rather than allowing arbitrary `status` assignment.