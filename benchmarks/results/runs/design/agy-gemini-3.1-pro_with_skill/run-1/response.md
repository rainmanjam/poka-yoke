## Subscription Model Design

This plan proposes the TypeScript types for the subscription model, applying poka-yoke design principles to ensure invalid states are unrepresentable.

## User Review Required
> [!IMPORTANT]
> The proposed types use a discriminated union instead of a single class or interface with optional fields. This means your functions will need to check the `status` field to access state-specific properties (e.g. `sub.status === 'canceled'` must be checked before accessing `sub.cancelReason`).

> [!NOTE]
> I replaced the `is_voluntary` boolean with an explicit `CancelType` string literal union (`'voluntary' | 'involuntary'`). This avoids the "boolean flag parameter" hazard where `true`/`false` lacks context at the call site. 

## Open Questions
> [!WARNING]
> 1. Are there specific literal values you want for `CancelReason` (e.g., `'payment_failed'`, `'user_requested'`), or should it remain a generic string for now?
> 2. How are you handling dates? I defaulted to JavaScript `Date` objects, but if you are passing these across the network, we might want to brand a string type like `IsoDateString`.

## Proposed Changes

### Subscription Types
We will create a new file for the subscription types. The design uses several poka-yoke devices:
1. **Branded Types**: `SubscriptionId` and `UserId` are branded strings so they cannot be accidentally swapped (Contact lens - adjacent same-type parameters).
2. **Discriminated Union**: `Subscription` is a union of exactly the 4 legal states. This prevents "bag-of-optionals" where an active sub could accidentally have a `cancelReason` (Contact lens - invalid states unrepresentable).
3. **Literal Unions**: `CancelType` and `CancelReason` use explicit literals instead of booleans/strings (Contact lens - boolean flag parameters and stringly-typed enums).

#### [NEW] types/subscription.ts
```typescript
// 1. Branded types for IDs to prevent swapping (e.g., passing a UserId where a SubscriptionId is expected)
declare const brand: unique symbol;
export type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type UserId = Brand<string, "UserId">;

// 2. Literal unions to replace ambiguous booleans and unconstrained strings
export type CancelType = "voluntary" | "involuntary";
export type CancelReason = "user_requested" | "payment_failed" | "fraud" | "upgrade"; // Example reasons

// 3. Base properties shared across all subscription states
interface BaseSubscription {
  id: SubscriptionId;
  userId: UserId;
}

// 4. Exact states modeled individually
export interface TrialingSubscription extends BaseSubscription {
  status: "trialing";
  trialEndDate: Date;
}

export interface ActiveSubscription extends BaseSubscription {
  status: "active";
  renewalDate: Date;
}

export interface PastDueSubscription extends BaseSubscription {
  status: "past_due";
  retryCount: number;
  gracePeriodEnd: Date;
}

export interface CanceledSubscription extends BaseSubscription {
  status: "canceled";
  cancelReason: CancelReason;
  cancelType: CancelType;
}

// 5. Discriminated union - makes invalid combinations (like active + cancelReason) unrepresentable
export type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;
```

## Verification Plan
### Automated Tests
To verify this works, we will write TypeScript compiler tests (using a tool like `ts-expect-error` or standard type assertions) to ensure that invalid assignments fail to compile. For example, trying to access `sub.cancelReason` when `sub.status === 'active'` should be a compiler error.

### Manual Verification
Review the types in `types/subscription.ts` to ensure they map correctly to your database schema and API contracts.