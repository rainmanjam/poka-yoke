This is a perfect use case for **discriminated unions** (tagged unions) in TypeScript. Each state has different required fields, so you want the type system to enforce that you can't access, say, a `trialEndDate` on an active subscription.

Here's the shape I'd recommend:

```typescript
type Subscription =
  | {
      status: 'trialing';
      trialEndDate: Date;
    }
  | {
      status: 'active';
      renewalDate: Date;
    }
  | {
      status: 'past_due';
      retryCount: number;
      gracePeriodEndDate: Date;
    }
  | {
      status: 'canceled';
      cancelReason: string;
      voluntary: boolean;
      canceledAt: Date;
    };
```

The `status` field is the discriminator — TypeScript uses it to narrow the type automatically:

```typescript
function handleSubscription(sub: Subscription) {
  if (sub.status === 'trialing') {
    console.log(sub.trialEndDate); // ✅ type-safe
  }
  // sub.trialEndDate would be a type error outside the narrowed block
}
```

**Why this matters:** You can't accidentally read `trialEndDate` from a canceled subscription, and you can't forget to check `voluntary` when handling cancellation. The type system catches state logic bugs at compile time.

**Trade-offs to consider:**
- **Shared fields?** If some states share fields (e.g., all have `createdAt` or `customerId`), you'd pull those out into a wrapper: `{ id: string; customerId: string; status: Subscription }` and make `Subscription` just the discriminated union of the state-specific fields.
- **Validation:** Do you want Zod or runtime validation to enforce that `retryCount >= 0`, or does your business logic guarantee it? (Learning mode question: where does validation live — at the API boundary, in the database layer, or both?)

Would you want to add a shared base with `id`, `customerId`, `createdAt`? Or add validation schemas on top?