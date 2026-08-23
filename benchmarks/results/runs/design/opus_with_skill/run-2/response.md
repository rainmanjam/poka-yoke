The file write needs permission I don't have in this session, so here it is inline. The core shape:

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };
export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId    = Brand<string, "CustomerId">;

// One fact, not two fields that can disagree.
export type Cancellation =
  | { kind: "voluntary";   reason: "too_expensive" | "missing_features" | "switched" | "other"; note?: string }
  | { kind: "involuntary"; reason: "payment_failed" | "fraud_dispute" | "compliance_hold" };

interface Base {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
  readonly planId: PlanId;
  readonly createdAt: Date;
}

export type Subscription = Base & (
  | { readonly status: "trialing"; readonly trialEndsAt: Date }
  | { readonly status: "active";   readonly renewsAt: Date }
  | { readonly status: "past_due"; readonly retryCount: RetryCount;
      readonly gracePeriodEndsAt: Date; readonly failedAt: Date }
  | { readonly status: "canceled"; readonly canceledAt: Date;
      readonly cancellation: Cancellation }
);
```

`sub.retryCount` is now inaccessible until you've narrowed to `past_due` — the compiler asks for the check instead of trusting you to remember it. Pair every switch with an `assertNever(x: never)` default arm so adding `paused` next year breaks the build at each site rather than falling through to "not active."

`★ Insight ─────────────────────────────────────`
Two things the union does **not** give you, and both bite:
- It stops you *describing* a nonsense subscription; it does not stop `canceled → past_due`, because a value of any variant is always constructible. That needs one `transition()` function as the only writer, plus an eslint `no-restricted-syntax` ban on assigning `.status` anywhere else.
- Types vanish at runtime. A migration or a psql session can still write an active row carrying a retry count. Mirror the union as a `CHECK (CASE status WHEN 'active' THEN retry_count IS NULL AND renews_at IS NOT NULL ...)`. A row-level CHECK can't police transitions though — it never sees `OLD.status`; canceled-is-terminal needs a `BEFORE UPDATE` trigger.
`─────────────────────────────────────────────────`

Also: brand `RetryCount` with a `0..MAX_RETRIES` parse, or the dunning loop has no termination condition in the type. And parse Stripe webhooks with `z.discriminatedUnion("status", [...])` — `JSON.parse` returns `any`, which is where all of the above dies.

**Left possible on purpose:** nothing enforces that `gracePeriodEndsAt > failedAt`, or that `renewsAt` is in the future. Cross-field date ordering is a runtime check in the parse, not a type.

**Your call, and it shouldn't be mine** — the transition table is billing policy:

1. `trialing` + payment_failed → `past_due` (dunning, keeps access through grace) or straight to `canceled`/involuntary? Dunning recovers real revenue and also gives free access to people who never paid.
2. Is `canceled` terminal? If reactivation writes a new row it stays terminal and churn cohorts stay honest; if it mutates the row, you silently lose the churn event.
3. At `retryCount === MAX_RETRIES`, who cancels — `transition()` or the cron job? If the cron, the state machine has two authors again.

Answer those three and I'll write `transition()` against them.