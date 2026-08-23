## Goal Description
You are building the subscription model for a SaaS platform in TypeScript. The subscription has four mutually exclusive states (`trialing`, `active`, `past_due`, `canceled`), each with specific fields that only apply when the subscription is in that state. 

Using a TypeScript **Discriminated Union** is the best approach here. It allows the TypeScript compiler to understand that checking the `status` field narrows down the type, preventing you from accidentally accessing a field like `trialEndDate` on an `active` subscription.

## Proposed Changes

Here is the proposed type definitions for the subscription model.

### Subscription Types

```typescript
// Common fields shared across all subscription states
export type SubscriptionBase = {
  id: string;
  userId: string;
  planId: string;
  createdAt: Date;
  updatedAt: Date;
};

export type TrialingSubscription = SubscriptionBase & {
  status: 'trialing';
  trialEndDate: Date;
};

export type ActiveSubscription = SubscriptionBase & {
  status: 'active';
  renewalDate: Date;
};

export type PastDueSubscription = SubscriptionBase & {
  status: 'past_due';
  retryCount: number;
  gracePeriodEnd: Date;
};

export type CanceledSubscription = SubscriptionBase & {
  status: 'canceled';
  cancelReason: string;
  isVoluntary: boolean;
};

// The Discriminated Union
export type Subscription = 
  | TrialingSubscription 
  | ActiveSubscription 
  | PastDueSubscription 
  | CanceledSubscription;
```

#### Example Usage

With these types, TypeScript will enforce strict checks based on the status:

```typescript
function handleSubscription(sub: Subscription) {
  switch (sub.status) {
    case 'trialing':
      // TypeScript knows sub is TrialingSubscription here
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
    default:
      // Exhaustiveness check
      const _exhaustiveCheck: never = sub;
      return _exhaustiveCheck;
  }
}
```

## Open Questions

> [!IMPORTANT]
> 1. **Base Fields:** I added some common base fields (`id`, `userId`, `planId`, `createdAt`, `updatedAt`). Are there any others you'd like to include in the `SubscriptionBase` type (e.g. `stripeCustomerId`, `priceId`)?
> 2. **File Location:** Where in your project would you like this types file to be created (e.g. `src/types/subscription.ts`)? Since I didn't see an obvious `src/` folder for TypeScript in the workspace root, I'd like to know where to save it.

## Verification Plan

### Manual Verification
- Review the proposed TypeScript types to ensure they cover all your business requirements.
- Once we agree on a file path, I will create the file and you can import and test it in your application code.