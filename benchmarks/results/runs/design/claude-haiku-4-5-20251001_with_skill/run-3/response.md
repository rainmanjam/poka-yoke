Perfect. Now I can apply the design method to your subscription model.

## Enumerating misuse

Before we pick the shape, here's what could go wrong:

1. **Invalid state combinations** — a subscription could be marked `active` with a `trialEndDate` and `gracePeriodEnd` both set, which is nonsense. With optional bags, you can express 2^N states; only ~4 actually exist.
2. **Mixing up temporal fields** — `trialEndDate` and `gracePeriodEnd` are both `Date`, so accessing the wrong one on the wrong state is a silent type error.
3. **Missing required context** — code that receives a `Subscription` must remember which fields exist on which state. Forgetting that is one more place a defect hides.
4. **Accidental state transitions** — the type should guide which states you can transition *to* from which states. A subscription shouldn't jump from trialing directly to canceled without passing through active or past_due.

## The design: discriminated unions

Use TypeScript's discriminated union to make each state its own type, so only the fields that actually exist can be accessed without a type guard:

```ts
type Subscription =
  | {
      status: "trialing";
      trialEndDate: Date;
    }
  | {
      status: "active";
      renewalDate: Date;
    }
  | {
      status: "past_due";
      retryCount: number;
      gracePeriodEnd: Date;
    }
  | {
      status: "canceled";
      cancelReason: string; // or enum if you know the possible reasons
      isVoluntary: boolean;
    };
```

**Rung reached: Control (contact lens).** Invalid states are now unrepresentable — if you have a value of type `Subscription`, it is guaranteed to be one of these four shapes, with exactly the right fields. Attempting to access `subscription.retryCount` on a trialing subscription is a compile error.

## Secondary considerations

1. **`cancelReason` should be an enum**, not a string, so you get exhaustiveness on what reasons are valid:
   ```ts
   type CancelReason = "payment_failed" | "user_requested" | "fraud" | "churn";
   ```
   This is move 4 from the design (fixed-value lens): adding a new reason later will break the build at every `switch` that handles it.

2. **Idempotency for retries** — when you retry a past_due subscription, you need that to be idempotent (so the same retry key doesn't double-charge). That goes in the *operation* signature, not the type:
   ```ts
   function retryPayment(
     subscription: Subscription & { status: "past_due" },
     idempotencyKey: IdempotencyKey
   ): Promise<Subscription>;
   ```
   This is move 3 from the design (motion-step lens): idempotency keys required, not optional.

3. **Temporal ordering** — `trialEndDate` on a `trialing` subscription should be in the future, `renewalDate` on `active` could be either way. If you want to enforce this, you can add runtime validation at the boundary (where subscriptions enter your system from the database or API), using Zod or a parse function. This is move 2 (parse, don't validate) at the system edge.

**What's possible but not prevented:** transitions between states. The type doesn't prevent jumping from `trialing` to `canceled` — that's a domain rule, not a shape rule. Enforce it in your state machine logic and with a database constraint if needed.

Should I write out the full implementation with these pieces, or does this direction work for you?