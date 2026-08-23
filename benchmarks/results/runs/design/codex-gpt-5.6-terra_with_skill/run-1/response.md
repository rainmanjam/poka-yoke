Use a discriminated union, not one record full of optional fields:

```ts
declare const brand: unique symbol;
type Brand<T, Name extends string> = T & {
  readonly [brand]: Name;
};

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type UtcInstant = Brand<string, "UtcInstant">;
export type RetryCount = Brand<number, "RetryCount">;
export type CancellationReason = Brand<string, "CancellationReason">;

export type Cancellation =
  | { kind: "voluntary"; reason: CancellationReason }
  | { kind: "involuntary"; reason: CancellationReason };

type SubscriptionBase = {
  id: SubscriptionId;
};

export type Subscription =
  | (SubscriptionBase & {
      status: "trialing";
      trialEndsAt: UtcInstant;
    })
  | (SubscriptionBase & {
      status: "active";
      renewsAt: UtcInstant;
    })
  | (SubscriptionBase & {
      status: "past_due";
      retryCount: RetryCount;
      gracePeriodEndsAt: UtcInstant;
    })
  | (SubscriptionBase & {
      status: "canceled";
      cancellation: Cancellation;
    });
```

Create the branded values only at your API/database boundary:

```ts
export function parseRetryCount(value: number): RetryCount {
  if (!Number.isInteger(value) || value < 0) {
    throw new Error("retryCount must be a non-negative integer");
  }
  return value as RetryCount;
}

export function parseUtcInstant(value: string): UtcInstant {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    throw new Error("Expected a valid timestamp");
  }
  return date.toISOString() as UtcInstant;
}

export function parseCancellationReason(value: string): CancellationReason {
  if (value.trim() === "") throw new Error("Cancellation reason is required");
  return value as CancellationReason;
}
```

This is a control-rung device: a canceled subscription cannot accidentally carry retry fields, and a trialing subscription cannot omit its trial end. Use exhaustive switches when consuming it, and keep status changes behind one transition function—types protect valid shapes, while that function protects valid lifecycle transitions.