Use a **discriminated union** — each status becomes a separate type branch, so TypeScript forces you to handle all cases and prevents invalid state combinations:

```typescript
type Subscription = 
  | { status: 'trialing'; trial_end_date: Date }
  | { status: 'active'; renewal_date: Date }
  | { status: 'past_due'; retry_count: number; grace_period_end: Date }
  | { status: 'canceled'; cancel_reason: string; was_voluntary: boolean };
```

Or with named interfaces for readability:

```typescript
interface TrialingSubscription {
  status: 'trialing';
  trial_end_date: Date;
}

interface ActiveSubscription {
  status: 'active';
  renewal_date: Date;
}

interface PastDueSubscription {
  status: 'past_due';
  retry_count: number;
  grace_period_end: Date;
}

interface CanceledSubscription {
  status: 'canceled';
  cancel_reason: string;
  was_voluntary: boolean;
}

type Subscription = 
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;
```

**Key benefit:** TypeScript's control flow analysis narrows the type automatically. When you check `sub.status === 'past_due'`, you can access `retry_count` and `grace_period_end` without casting. Accessing the wrong field on the wrong state is a compile error.

You can also enforce exhaustiveness with a helper:

```typescript
function handleSubscription(sub: Subscription): string {
  switch (sub.status) {
    case 'trialing':
      return `Trial ends ${sub.trial_end_date}`;
    case 'active':
      return `Renews ${sub.renewal_date}`;
    case 'past_due':
      return `${sub.retry_count} retries, grace until ${sub.grace_period_end}`;
    case 'canceled':
      return `Canceled (${sub.was_voluntary ? 'voluntary' : 'involuntary'}): ${sub.cancel_reason}`;
  }
  // TypeScript error if you forget a case
  const _exhaustive: never = sub;
  return _exhaustive;
}
```

The second version (interfaces) scales better if any state will grow more fields later. Pick whichever fits your codebase's style.