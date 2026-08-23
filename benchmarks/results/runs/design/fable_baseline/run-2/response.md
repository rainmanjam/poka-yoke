The skill's core move for this exact shape is a discriminated union keyed on `status`. Misuses I'm designing against:

1. A bag of optionals (`trialEndsAt?`, `retryCount?`, `cancelReason?`…) claims 2^7 states are legal; four are.
2. A `switch` on status that silently ignores a fifth status added next year.
3. `retryCount` of -1 or 9000, and `voluntary` defaulting to something when nobody set it.

```ts
type SubscriptionId = string & { readonly __brand: "SubscriptionId" };
type CustomerId = string & { readonly __brand: "CustomerId" };

interface SubscriptionBase {
  id: SubscriptionId;
  customerId: CustomerId;
  planId: string;
}

type CancelReason =
  | "customer_request"
  | "payment_failed"
  | "fraud"
  | "plan_retired";

type Subscription =
  | (SubscriptionBase & { status: "trialing"; trialEndsAt: Date })
  | (SubscriptionBase & { status: "active";   renewsAt: Date })
  | (SubscriptionBase & {
      status: "past_due";
      retryCount: number;       // see note on bounding below
      gracePeriodEndsAt: Date;
    })
  | (SubscriptionBase & {
      status: "canceled";
      reason: CancelReason;
      voluntary: boolean;
    });

// Exhaustiveness: adding a fifth status breaks the build at every site that must change.
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

function nextBillingEvent(sub: Subscription): Date | null {
  switch (sub.status) {
    case "trialing": return sub.trialEndsAt;
    case "active":   return sub.renewsAt;
    case "past_due": return sub.gracePeriodEndsAt;
    case "canceled": return null;
    default:         return assertNever(sub);
  }
}
```

Why this shape:

- **Narrowing is free.** After `if (sub.status === "past_due")`, `sub.retryCount` is a `number`, not `number | undefined`. No `!`, no defensive `?? 0`.
- **The illegal states have no spelling.** You cannot construct an active sub with a cancel reason, or a canceled one without `voluntary`.
- **`assertNever` is the highest-leverage line here.** Without it, a new `"paused"` status compiles and falls through every switch silently.

What I deliberately left possible:

- `retryCount` is a bare `number`; TS can't express `0..5`. If you cap retries, bound it at the boundary (a `parseSubscription` from your DB/Stripe payload that throws on out-of-range) or make it a literal union `0 | 1 | 2 | 3 | 4 | 5` if the cap is fixed.
- `voluntary` and `reason` overlap — `"payment_failed"` is never voluntary. If that correlation is strict, fold it into the reason type and drop the boolean; two fields that must agree is a bag-of-optionals in miniature.
- Plain `Date`s. If you're mixing Stripe's epoch seconds with JS millis anywhere, brand the timestamp too.

One question for you (it changes the design, so it's worth answering): is `voluntary` derivable from `reason`? If yes, delete the boolean.