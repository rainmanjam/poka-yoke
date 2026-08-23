Following the **design** mode from your poka-yoke system. Let me work through the ritual before the code.

## Enumerate misuse first

For your subscription model, the hazards are:

1. **Impossible combinations**: A trialing sub shouldn't have a `retryCount`. An active sub shouldn't have a `gracePeriodEnd`. Canceled subs must carry *both* reason and voluntary flag together.
2. **Required fields**: Callers can forget to provide `retryCount` on a past_due sub, or forget the `cancelReason` on a canceled one. Bag-of-optionals hides these.
3. **Silent completeness failure**: When you add a new status next year (e.g., `suspended`), what happens to `if (sub.status === 'active') { ... }`? Ideally: the build breaks.
4. **Callers forgetting state-specific logic**: If someone reads `.retryCount` without checking the status first, that's a silent bug—the value doesn't exist.

## Design: discriminated union (Control rung, contact lens)

TypeScript discriminated unions make every invalid combination unsayable:

```typescript
type Subscription = 
  | { status: 'trialing'; trialEndDate: Date }
  | { status: 'active'; renewalDate: Date }
  | { status: 'past_due'; retryCount: number; gracePeriodEnd: Date }
  | { status: 'canceled'; cancelReason: string; isVoluntary: boolean }
```

## Why this fixes your hazards

- ✓ **Impossible combinations gone** — you literally cannot write `{ status: 'trialing', retryCount: 5 }`. The type won't compile.
- ✓ **Required fields enforced** — omit `renewalDate` on an active sub and TypeScript catches it.
- ✓ **Exhaustiveness at build time** — a switch over `sub.status` requires a case for every variant. Add `suspended` and every unhandled site breaks the build, not silently falls through.
- ✓ **No unsafe field access** — inside `if (sub.status === 'past_due') { ... }`, you can access `sub.retryCount` safely; outside that guard, TypeScript rejects it.

## When you add a new status

Add it to the union, and your entire codebase lights red until you handle it. That's the device working.

Write the types in your model file, then open them to the specific decision on `cancelReason` and `isVoluntary`: should canceled subs express what *kind* of cancellation? A stricter approach would be a nested discriminated union:

```typescript
| { status: 'canceled'; cancellation: 
    | { type: 'voluntary'; reason: string }
    | { type: 'involuntary'; reason: string }
  }
```

That's optional — depends on whether you need to distinguish the two kinds in downstream code. Keep it simple if the callers don't care.