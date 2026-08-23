## Goal Description
The goal is to design TypeScript types for a SaaS subscription model that correctly represent the distinct states a subscription can be in: trialing, active, past_due, and canceled. Each state has specific fields that only apply to it.

## Open Questions
- Do subscriptions have unique IDs or other shared metadata (e.g., `userId`, `planId`) that should be included in all states? I have included a branded `SubscriptionId` as a placeholder for this common data.
- Are there any other states, like `paused` or `unpaid`?

## Proposed Changes
I propose using a **discriminated union** (Control, contact lens) to model the subscription.

### TypeScript Interfaces

```typescript
// Branded type for Subscription IDs to prevent mixing with other strings (Control, contact lens)
export type SubscriptionId = string & { readonly __brand: unique symbol };

// Common fields shared across all subscription states
interface BaseSubscription {
  id: SubscriptionId;
  // userId: UserId; 
  // planId: PlanId;
}

export type TrialingSubscription = BaseSubscription & {
  status: 'trialing';
  trialEndDate: Date;
};

export type ActiveSubscription = BaseSubscription & {
  status: 'active';
  renewalDate: Date;
};

export type PastDueSubscription = BaseSubscription & {
  status: 'past_due';
  retryCount: number;
  gracePeriodEnd: Date;
};

export type CanceledSubscription = BaseSubscription & {
  status: 'canceled';
  cancelReason: string;
  isVoluntary: boolean;
};

export type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;
```

### Poka-Yoke Reasoning

**Misuses Enumerated:**
1. A single `Subscription` struct with optional fields (`trialEndDate?`, `retryCount?`) allows invalid states, such as a "trialing" subscription with a "cancel reason".
2. Passing arbitrary strings as subscription IDs could lead to mixing them up with user IDs or plan IDs.
3. Switch statements on the `status` string might forget to handle a state (e.g., forgetting `past_due`).

**What the design makes impossible:**
1. **Bag-of-optionals hazard (C8):** By using a discriminated union on `status`, the type system enforces that you cannot access `retryCount` unless you have explicitly narrowed the status to `'past_due'`. This reaches **Control (Rung 1)**.
2. **Primitive obsession (C1/C3):** By using a branded type `SubscriptionId`, we prevent accidental swaps with other IDs. This reaches **Control (Rung 1)**.
3. **Non-exhaustive branching (F1):** The discriminated union allows the TypeScript compiler to ensure all switch statements on `status` are exhaustive (if used with a never-assertion or `switch-exhaustiveness-check` linting). This reaches **Control (Rung 1)**.

**What is left possible:**
- We didn't add typestate constraints to restrict *transitions* between these states (e.g., preventing a transition from `canceled` directly to `trialing`), because these are just data transfer types. State transition rules would need to be enforced by the functions mutating the subscription (Motion-step lens).
- We assume `Date` is used correctly. If timezones are a concern, a dedicated timezone-aware type or parsing library is recommended (C9).

## Verification Plan
### Automated Tests
Run `tsc --noEmit` on the file where these types will be placed to verify that TypeScript correctly enforces the discriminated union properties.

### Manual Verification
Ensure that attempting to access `subscription.retryCount` without checking `if (subscription.status === 'past_due')` results in a TypeScript compilation error.