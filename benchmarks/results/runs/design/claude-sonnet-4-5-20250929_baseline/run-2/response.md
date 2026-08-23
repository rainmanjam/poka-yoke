I'm creating a type-safe subscription model using **discriminated unions** to prevent invalid state combinations.

`★ Insight ─────────────────────────────────────`
**Discriminated unions** make invalid states unrepresentable. A string-based status like `status: "canceled"` lets you accidentally access `renewal_date` on a canceled subscription. A discriminated union makes TypeScript prevent that at compile time.

**Bounded types** prevent logic errors. An unbounded `retryCount: number` could theoretically reach 1000. Restricting it to `0 | 1 | 2 | 3` documents the retry policy in the type and catches bugs where retry logic goes infinite.

**Branded types** prevent ID mixups. Without branding, TypeScript sees both `subscriptionId` and `customerId` as plain strings, so you can accidentally pass one where the other is expected.
`─────────────────────────────────────────────────`

## The Design

**Four separate types** (one per state):
- `TrialingSubscription` → has `trialEndDate`
- `ActiveSubscription` → has `renewalDate`  
- `PastDueSubscription` → has `retryCount: 0|1|2|3` and `gracePeriodEnd`
- `CanceledSubscription` → has `cancelReason` enum and `voluntary: boolean`

**The union**: `type Subscription = TrialingSubscription | ActiveSubscription | ...`

**Exhaustiveness checking**: The `switch` statement on `status` will cause a TypeScript error if you add a new state but forget to handle it.

The file includes type guards (`isTrialing()`, `isActive()`, etc.) and an example function showing how TypeScript narrows the type based on the `status` field.

**What's left for you to decide**: The TODO at the bottom marks where state transition functions would go. You'll need to define which transitions are legal (e.g., can a canceled subscription go back to trialing? Can past_due skip straight to canceled after 3 retries?).

Creating `src/subscription-types.ts` now...