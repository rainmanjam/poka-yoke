The design skill points me to your exact situation: **discriminated unions** make invalid states unrepresentable. Let me work through this using the design ritual first.

## Enumerate misuse

What could go wrong with subscription state?

1. **Caller forgets to check state before accessing fields** — like reading `renewal_date` on a canceled subscription.
2. **A function receives a subscription but can't rely on which fields exist** — it either crashes, or has to defensively check everything.
3. **Adding a new state later breaks silently** — code just skips it.
4. **Fields exist for the wrong state** — a trialing subscription gets a retry count, or a canceled one has a renewal date.

## The solution

Use a **discriminated union** where each state branch declares exactly its own fields. This moves the check from "did the caller remember to validate?" into "can the code even compile?":

```ts
type Subscription =
  | { status: "trialing"; trialEndDate: Date }
  | { status: "active"; renewalDate: Date }
  | {
      status: "past_due";
      retryCount: number;
      gracePeriodEndDate: Date;
    }
  | {
      status: "canceled";
      cancelReason: string;
      wasVoluntary: boolean;
    };
```

Now:
- **`subscription.trialEndDate` is a compile error** unless the type system has narrowed to `status: "trialing"`.
- **Adding a state breaks the build** at every `switch` that must handle it.
- **The database schema can enforce it** with a `CHECK` constraint or by storing state as a JSONB blob with a schema validator.

## Exhaustive handling pattern

At every site that reads subscription state, use exhaustive matching:

```ts
function getRenewalDate(sub: Subscription): Date | null {
  switch (sub.status) {
    case "trialing":
      return sub.trialEndDate; // TypeScript knows this field exists
    case "active":
      return sub.renewalDate;
    case "past_due":
      return sub.gracePeriodEndDate;
    case "canceled":
      return null; // No renewal for canceled
    default:
      assertNever(sub); // Breaks the build if a case is missing
  }
}

function assertNever(x: never): never {
  throw new Error(`Unhandled status: ${JSON.stringify(x)}`);
}
```

Enforce `@typescript-eslint/switch-exhaustiveness-check` in CI so this pattern can't be circumvented.

## Optional: branded types for higher-precision fields

If retry counts or dates should never be negative/invalid, consider:

```ts
type RetryCount = number & { readonly __brand: "RetryCount" };
const RetryCount = (n: number): RetryCount => {
  if (n < 0) throw new Error("Retry count must be non-negative");
  return n as RetryCount;
};
```

This prevents passing arbitrary numbers where only valid counts belong, but it's only worth the boilerplate if these values cross API boundaries or are frequently misused. For internal types, the discriminated union is usually enough.

**This design reaches Control rung** — invalid states are impossible to express in the type system. The only thing a caller could plausibly forget is exhaustive handling, and that's caught by the lint rule, which is Control at CI time.