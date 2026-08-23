This is a textbook case for a discriminated union — each state carries different data, and you want TypeScript to enforce that you can't access `cancelReason` on an active subscription.

```typescript
type Subscription =
  | { status: 'trialing'; trialEndDate: Date }
  | { status: 'active'; renewalDate: Date }
  | { status: 'past_due'; retryCount: number; gracePeriodEnd: Date }
  | { status: 'canceled'; cancelReason: string; voluntary: boolean };
```

`★ Insight ─────────────────────────────────────`
**Why discriminated unions here?** The `status` field acts as a "tag" that TypeScript uses to narrow the type. When you check `if (sub.status === 'past_due')`, TS knows `retryCount` and `gracePeriodEnd` exist — no casting, no optional chaining on fields that must be present.

**Impossible states become unrepresentable.** You literally cannot construct a subscription with both `trialEndDate` and `cancelReason` — the compiler rejects it. This catches bugs at compile time that runtime validation would miss.
`─────────────────────────────────────────────────`

One decision for you: should `canceled` subscriptions preserve when they were canceled? Right now you'd lose that — adding `canceledAt: Date` to that variant is common. Same question for `past_due` — do you need to know when it first went past due, or just the grace period deadline?