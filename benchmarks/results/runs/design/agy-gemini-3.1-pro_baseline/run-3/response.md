## Goal Description
The goal is to design TypeScript types for a SaaS subscription model where subscriptions can have one of four statuses: `trialing`, `active`, `past_due`, or `canceled`. Each status has its own specific fields.

## Proposed Changes
The best approach for this in TypeScript is using a **Discriminated Union** (also known as a tagged union). This allows TypeScript to automatically narrow down the exact type based on a shared property (the discriminator, typically `status`). This ensures you can't accidentally access fields that don't belong to the current status.

We can define a base interface for common fields that all subscriptions share, and then extend it for each specific status.

### [NEW] `types/subscription.ts` (Example file)

```typescript
// Shared fields for all subscriptions
export interface BaseSubscription {
  id: string;
  customerId: string;
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
  wasVoluntary: boolean;
}

// The discriminated union type
export type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;
```

With this setup, TypeScript will enforce type safety and provide excellent autocomplete. For example:

```typescript
function handleSubscription(sub: Subscription) {
  // We can always access common fields
  console.log(sub.id); 

  if (sub.status === 'past_due') {
    // TypeScript knows `sub` is PastDueSubscription inside this block
    console.log(`Retries: ${sub.retryCount}`);
    
    // console.log(sub.trialEndDate); // ❌ Error: Property 'trialEndDate' does not exist
  }
}
```

## Open Questions
> [!IMPORTANT]
> 1. **Common Fields:** What common fields should all subscriptions share? I've included `id`, `customerId`, `planId`, `createdAt`, and `updatedAt` as a starting point.
> 2. **Date Types:** Are you representing dates as JavaScript `Date` objects, ISO strings, or timestamps (numbers)? (Often when working with APIs, these are ISO strings).
> 3. **Enums vs. Strings:** Would you prefer to use a TypeScript `enum` for the status values instead of string literals (e.g., `SubscriptionStatus.TRIALING`)?

## Verification Plan
Please review the proposed design. Once you are happy with the types and answer the open questions, I can write the actual files to your project or help you build functions that use these types.