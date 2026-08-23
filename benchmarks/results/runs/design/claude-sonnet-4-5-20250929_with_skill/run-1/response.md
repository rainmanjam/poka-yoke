★ Insight ─────────────────────────────────────
Following poka-yoke design principles: enumerating misuses first, then designing types that make invalid states unrepresentable. The hazard here is **C8: bag-of-optionals** — a flat struct with optional fields permits 2^N impossible states.
─────────────────────────────────────────────────

## Misuse enumeration (before writing the type)

Your description reveals several invalid states we need to make impossible:

1. **Trialing with a cancel_reason** — nonsense combination
2. **Active with a retry_count** — active subscriptions aren't retrying
3. **Canceled with a grace_period_end** — canceled is terminal
4. **Past_due with a trial_end_date** — past-due implies billing already started
5. **Unbounded retry_count** — could retry forever
6. **Canceled with missing reason** — might be okay if voluntary, but needs structure

The strongest device here is a **discriminated union** (Contact lens, Control rung) — make each state carry exactly its fields, so impossible combinations have no spelling.

## The design

```typescript
// Branded types for dates (optional but recommended)
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };
type TrialEndDate = Brand<Date, "TrialEndDate">;
type RenewalDate = Brand<Date, "RenewalDate">;
type GracePeriodEnd = Brand<Date, "GracePeriodEnd">;

// Bounded retry count (0-3 per your requirements)
type RetryCount = 0 | 1 | 2 | 3;

// Nested cancellation structure to handle voluntary vs involuntary
type Cancellation =
  | { voluntary: true; reason?: string }
  | { voluntary: false; reason: string }; // Non-voluntary requires a reason

// Discriminated union — each status carries exactly its data
type Subscription =
  | {
      status: "trialing";
      trial_end_date: TrialEndDate;
    }
  | {
      status: "active";
      renewal_date: RenewalDate;
    }
  | {
      status: "past_due";
      retry_count: RetryCount;
      grace_period_end: GracePeriodEnd;
    }
  | {
      status: "canceled";
      cancellation: Cancellation;
    };
```

## What we achieved

| Misuse | Prevented how | Rung |
|--------|---------------|------|
| Trialing subscription with retry_count | Property doesn't exist on that variant | **Control** |
| Active subscription with cancel_reason | Property doesn't exist on that variant | **Control** |
| Retry count > 3 | Literal union type only permits 0\|1\|2\|3 | **Control** |
| Non-voluntary cancellation with no reason | Discriminated union requires `reason` when `voluntary: false` | **Control** |
| New status added next year | Exhaustive switch breaks the build (see below) | **Control** |

## Using it with exhaustive matching

```typescript
function assertNever(x: never): never {
  throw new Error(`Unhandled variant: ${JSON.stringify(x)}`);
}

function renderSubscription(sub: Subscription): string {
  switch (sub.status) {
    case "trialing":
      return `Trial ends ${sub.trial_end_date.toISOString()}`;
    case "active":
      return `Renews ${sub.renewal_date.toISOString()}`;
    case "past_due":
      return `Grace period ends ${sub.grace_period_end.toISOString()} (retry ${sub.retry_count}/3)`;
    case "canceled":
      return sub.cancellation.voluntary
        ? `Canceled by user${sub.cancellation.reason ? `: ${sub.cancellation.reason}` : ""}`
        : `Canceled: ${sub.cancellation.reason}`;
    default:
      return assertNever(sub); // Breaks the build if a status is added
  }
}
```

## Tradeoffs consciously left

- **Branded dates are optional** — I included them for maximum safety (prevents swapping `trial_end_date` and `renewal_date`), but they add ceremony. Drop the branding if the extra safety isn't worth it.
- **Voluntary cancellations can omit reason** — I modeled this as `reason?` on the voluntary branch. If you want to *require* a reason even for voluntary cancellations, remove the `?`.
- **No runtime validation shown** — this is compile-time only. At your API boundary, parse with Zod:
  ```typescript
  import { z } from "zod";
  
  const SubscriptionSchema = z.discriminatedUnion("status", [
    z.object({ status: z.literal("trialing"), trial_end_date: z.coerce.date() }),
    z.object({ status: z.literal("active"), renewal_date: z.coerce.date() }),
    z.object({
      status: z.literal("past_due"),
      retry_count: z.union([z.literal(0), z.literal(1), z.literal(2), z.literal(3)]),
      grace_period_end: z.coerce.date(),
    }),
    z.object({
      status: z.literal("canceled"),
      cancellation: z.discriminatedUnion("voluntary", [
        z.object({ voluntary: z.literal(true), reason: z.string().optional() }),
        z.object({ voluntary: z.literal(false), reason: z.string() }),
      ]),
    }),
  ]);
  ```

Would you like me to adjust the cancellation logic, add state transition functions, or show how to enforce this at the database level with a `CHECK` constraint?