Here's the type design:

```typescript
// Branded type for retry count - prevents values outside 0-3 range
type RetryCount = 0 | 1 | 2 | 3;

// Discriminated union for cancellation - prevents invalid combinations
type Cancellation =
  | { voluntary: true; reason: 'user_requested' | 'downgrade' }
  | { voluntary: false; reason: 'payment_failed' | 'fraud' | 'policy_violation' };

// Base subscription fields (common to all states)
interface BaseSubscription {
  id: string;
  customerId: string;
  planId: string;
  currentPeriodStart: Date;
  currentPeriodEnd: Date;
}

// State-specific subscriptions using discriminated union
type Subscription =
  | (BaseSubscription & {
      status: 'trialing';
      trialEndDate: Date;
    })
  | (BaseSubscription & {
      status: 'active';
      nextRenewalDate: Date;
    })
  | (BaseSubscription & {
      status: 'past_due';
      retryCount: RetryCount;
      gracePeriodEnd: Date;
      nextRetryDate: Date; // useful for UI
    })
  | (BaseSubscription & {
      status: 'canceled';
      canceledAt: Date;
      cancellation: Cancellation;
    });

// Example: exhaustiveness-checked status handler
function handleSubscription(sub: Subscription): string {
  switch (sub.status) {
    case 'trialing':
      return `Trial ends ${sub.trialEndDate.toISOString()}`;
    case 'active':
      return `Renews ${sub.nextRenewalDate.toISOString()}`;
    case 'past_due':
      return `Retry ${sub.retryCount}/3, grace ends ${sub.gracePeriodEnd.toISOString()}`;
    case 'canceled':
      return `Canceled (${sub.cancellation.voluntary ? 'voluntary' : 'involuntary'}): ${sub.cancellation.reason}`;
    default:
      const _exhaustive: never = sub;
      return _exhaustive;
  }
}
```

**Key design decisions:**

1. **Discriminated union on `status`** - TypeScript narrows properties based on status, preventing access to `trialEndDate` on non-trialing subscriptions
2. **Bounded `RetryCount`** - Can't exceed 3 retries; compiler enforces this
3. **Nested discriminated union for cancellation** - Prevents "voluntary cancellation due to payment failure" contradictions
4. **Exhaustiveness checking** - The `never` type in the default case means TypeScript will error if you add a new status but forget to handle it

This makes invalid states unrepresentable at compile-time rather than catching them at runtime.