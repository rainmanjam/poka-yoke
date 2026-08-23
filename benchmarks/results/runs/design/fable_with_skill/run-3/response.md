Routed to `design` mode. Applying the ritual: enumerate misuse first, then the shape.

**Misuses the types must make unsayable**

1. **Bag of optionals** — `{ status, trialEndsAt?, retryCount?, graceEndsAt?, cancelReason?, voluntary?, renewsAt? }` claims 2⁷ states; you have four. "past_due with a cancel reason" becomes reachable and every consumer guesses differently.
2. **Adding a fifth status next year** (`paused`) — the right answer is "the build breaks at every switch."
3. **Illegal transitions** — `canceled → trialing`, or `status` assigned from six call sites.
4. **Naive dates and bare numbers** — `retryCount: number` admits `-1` and `3.5`; date-as-string admits timezone drift.

**The types**

```ts
// ---- Branded scalars (contact lens: the wrong thing can't fit) ----
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId     = Brand<string, "CustomerId">;
export type RetryCount     = Brand<number, "RetryCount">; // non-negative integer, via parse

// ---- Status as a closed union, not string ----
export type SubscriptionStatus = "trialing" | "active" | "past_due" | "canceled";

export type CancelReason =
  | "payment_failed"
  | "customer_request"
  | "fraud"
  | "plan_discontinued";

// ---- Common fields ----
interface SubscriptionBase {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
}

// ---- One variant per state. No optionals. ----
export type Subscription =
  | (SubscriptionBase & { readonly status: "trialing"; readonly trialEndsAt: Date })
  | (SubscriptionBase & { readonly status: "active";   readonly renewsAt: Date })
  | (SubscriptionBase & {
      readonly status: "past_due";
      readonly retryCount: RetryCount;
      readonly graceEndsAt: Date;
    })
  | (SubscriptionBase & {
      readonly status: "canceled";
      readonly reason: CancelReason;
      readonly voluntary: boolean;
      readonly canceledAt: Date;
    });

// Handy per-state aliases for function signatures
export type PastDueSubscription  = Extract<Subscription, { status: "past_due" }>;
export type CanceledSubscription = Extract<Subscription, { status: "canceled" }>;

// ---- Fixed-value lens: exhaustiveness ----
export function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

// ---- Motion-step lens: transitions only through typed functions ----
export function markPastDue(
  sub: Extract<Subscription, { status: "active" }>,
  graceEndsAt: Date,
): PastDueSubscription {
  return { id: sub.id, customerId: sub.customerId, status: "past_due",
           retryCount: 0 as RetryCount, graceEndsAt };
}
```

The transition function is the device for hazard 3: `markPastDue(canceledSub, …)` does not compile. One function per legal edge, and nothing else assigns `status`.

`★ Insight ─────────────────────────────────────`
- `Extract<Subscription, { status: "past_due" }>` as a parameter type means a function that retries payment *cannot receive* an active or canceled sub — the narrowing is done once at the edge and carried by the type.
- `voluntary` and `reason` are correlated. If `reason: "payment_failed"` can never be voluntary, consider splitting `canceled` into `canceled_voluntary | canceled_involuntary` with reason subsets per variant — it removes one more nonsense state, at the cost of a fifth arm in every switch. I left it as a boolean because you said "whether it was voluntary," suggesting it's independently recorded.
`─────────────────────────────────────────────────`

**Rungs reached**
- Bag-of-optionals, stringly status, swapped IDs: **Control** (compile error).
- New variant unhandled: **Control** once `assertNever` is in every switch; enforce repo-wide with `@typescript-eslint/switch-exhaustiveness-check` at `error`.
- Illegal transitions: **Control** in TS, but only in TS — a script hitting the DB directly bypasses it. Push it down with `CHECK ((status = 'past_due') = (retry_count IS NOT NULL))`-style constraints per field, and note a row-level CHECK still can't see the *previous* state; that needs a trigger.

**Consciously left possible**
- `Date` is not timezone-safe by type; treat UTC-at-rest as a convention until you adopt `Temporal`.
- `RetryCount` brand is a cast unless you give it a parse (`parseRetryCount(n): RetryCount | Error`) and ban `as RetryCount` outside it.
- Data crossing from Stripe/your DB must be parsed with a zod discriminated union at the boundary; these types are comments at runtime otherwise.

None of this is load-bearing without `strict: true` and `tsc --noEmit` as a required CI check.