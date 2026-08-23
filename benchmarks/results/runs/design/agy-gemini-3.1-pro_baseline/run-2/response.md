## Subscription Model Types
This plan outlines the TypeScript types for the SaaS subscription model. We will use a **discriminated union** based on the `status` field. This is a TypeScript best practice because it allows the compiler to narrow down the exact type of a subscription once you check its `status`, preventing you from accidentally accessing properties that shouldn't exist in that state (e.g., trying to read `cancelReason` on an `active` subscription).

## Open Questions
- **Shared Fields:** I've added some common fields like `id`, `userId`, `planId`, `createdAt`, and `updatedAt` to a `BaseSubscription` interface. Are there any other shared properties all subscriptions should have (e.g., `price`, `currency`)?
- **Date Types:** I used `Date` for the date fields (`trialEndDate`, `renewalDate`, etc.). Depending on your stack, you might prefer strings (ISO strings) or a library type (like `Moment` or `Dayjs`). Let me know if you have a preference.

## Proposed Changes

### [NEW] `types/subscription.ts` (or similar)
```typescript
export type SubscriptionStatus = 'trialing' | 'active' | 'past_due' | 'canceled';

// Shared properties that all subscriptions have
export interface BaseSubscription {
  id: string;
  userId: string;
  planId: string;
  createdAt: Date;
  updatedAt: Date;
}

export interface TrialingSubscription extends BaseSubscription {
  status: 'trialing';
  trialEndDate: Date;
}

export interface ActiveSubscription extends BaseSubscription {
  status: 'active';
  renewalDate: Date;
}

export interface PastDueSubscription extends BaseSubscription {
  status: 'past_due';
  retryCount: number;
  gracePeriodEnd: Date;
}

export interface CanceledSubscription extends BaseSubscription {
  status: 'canceled';
  cancelReason: string;
  isVoluntary: boolean; // true if user canceled, false if canceled due to payment failure etc.
}

// The main Subscription type is a discriminated union of all possible states
export type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;
```

### Example Usage (For context)
Because of the discriminated union, TypeScript will provide excellent autocompletion and type safety:

```typescript
function handleSubscription(sub: Subscription) {
  switch (sub.status) {
    case 'trialing':
      // TS knows 'sub' is TrialingSubscription here
      console.log(`Trial ends on: ${sub.trialEndDate}`);
      break;
    case 'active':
      console.log(`Renews on: ${sub.renewalDate}`);
      break;
    case 'past_due':
      console.log(`Retry count: ${sub.retryCount}, Grace period ends: ${sub.gracePeriodEnd}`);
      break;
    case 'canceled':
      console.log(`Canceled voluntarily? ${sub.isVoluntary}, Reason: ${sub.cancelReason}`);
      break;
  }
}
```