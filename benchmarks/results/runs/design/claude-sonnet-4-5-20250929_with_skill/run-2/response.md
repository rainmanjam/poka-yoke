★ Insight ─────────────────────────────────────
This is a textbook case of **C8: Bag-of-optionals** — a struct with several optional fields where only certain combinations are meaningful. The mistake-proofing move here is a **discriminated union** that makes invalid states literally unrepresentable.
─────────────────────────────────────────────────

Let me apply the poka-yoke design ritual to your subscription model.

## Hazards to prevent

**Before** designing the types, enumerate the misuses:

1. **Invalid state combinations** (C8) — Can we construct `{status: "active", cancelReason: "dunning_failed"}`? A bag of optionals permits this nonsense.
2. **Unbounded retry count** (F7) — Can `retryCount` be 9,999? That's not how dunning works.
3. **Non-exhaustive handling** (F1) — When someone adds `"paused"` next year, what breaks? With a string status, nothing — it silently falls through.
4. **Illegal transitions** (M3) — Can code transition from `canceled` back to `trialing`? Without a controlled transition function, yes.

## The types

```typescript
// Branded types for domain concepts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

type CancelReason = 
  | "payment_failed"
  | "user_requested" 
  | "dunning_exhausted"
  | "fraud";

// Discriminated union — exactly 4 states, no more
type Subscription =
  | {
      status: "trialing";
      trialEndDate: Date;
    }
  | {
      status: "active";
      renewalDate: Date;
    }
  | {
      status: "past_due";
      retryCount: 0 | 1 | 2 | 3;  // Bounded — dunning has a ceiling
      gracePeriodEnd: Date;
    }
  | {
      status: "canceled";
      cancelReason: CancelReason;
      wasVoluntary: boolean;
      canceledAt: Date;  // Added — you'll want this
    };

// Exhaustiveness helper
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

// Example: now the compiler forces you to handle every case
function getStatusMessage(sub: Subscription): string {
  switch (sub.status) {
    case "trialing":
      return `Trial ends ${sub.trialEndDate.toDateString()}`;
    case "active":
      return `Renews ${sub.renewalDate.toDateString()}`;
    case "past_due":
      return `Retry ${sub.retryCount}/3, grace until ${sub.gracePeriodEnd.toDateString()}`;
    case "canceled":
      return `Canceled: ${sub.cancelReason}`;
    default:
      return assertNever(sub);  // Compile error if a case is missing
  }
}
```

## What this achieves

| Hazard | Device | Rung |
|--------|--------|------|
| "Active subscription with a cancel reason" | Discriminated union — the combination has no representation | **Control** |
| `retryCount: 9999` | Literal union `0 \| 1 \| 2 \| 3` — only valid values typecheck | **Control** |
| Adding `"paused"` status but forgetting to handle it | Exhaustive switch with `assertNever` — breaks the build | **Control** |
| `cancelReason: "oops"` | Literal union — typos and invalid reasons don't compile | **Control** |

## What's deliberately left possible

- **State transitions** — This type doesn't *enforce* that you can't go from `canceled` to `active`. That's an M3 hazard (illegal state transitions) and the device for it is a **transition function** that's the only legal way to change status:

```typescript
type TransitionResult = 
  | { ok: true; subscription: Subscription }
  | { ok: false; reason: string };

function transition(
  from: Subscription,
  to: Subscription["status"],
  // ... other required params per transition
): TransitionResult {
  // Single place that knows the legal moves
  if (from.status === "canceled") {
    return { ok: false, reason: "Cannot transition from canceled" };
  }
  // ... rest of state machine
}
```

That's the **motion-step device** (M3) and it reaches **Control** if you make this the only way to update the status field (e.g., the database setter is private and only the transition function can call it).

Would you like me to implement the full transition function with the legal moves enforced?