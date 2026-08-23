No existing subscription model in this repo — those hits are just benchmark scenario files, unrelated. This is a fresh design question, so here's the type design.

## Enumerate the misuse first

- **Bag-of-optionals trap**: if you model this as one `Subscription` type with `trialEndDate?`, `retryCount?`, `gracePeriodEnd?`, `cancelReason?`, `voluntary?`, `renewalDate?` all optional, TypeScript lets you construct a `canceled` subscription that also has a `renewalDate`, or a `past_due` one missing `gracePeriodEnd`. Nothing stops it.
- **Adjacent same-typed fields**: `trialEndDate`, `gracePeriodEnd`, `renewalDate` are all `Date` — easy to assign the wrong one if they're separate optional properties on one flat object.
- **New status added later**: someone adds `paused` next year. You want the compiler to fail at every `switch` that handles status, not silently fall through a default branch.

## The types

```typescript
type SubscriptionId = string & { readonly __brand: "SubscriptionId" };

interface SubscriptionBase {
  id: SubscriptionId;
  customerId: string;
  planId: string;
}

interface TrialingSubscription extends SubscriptionBase {
  status: "trialing";
  trialEndDate: Date;
}

interface ActiveSubscription extends SubscriptionBase {
  status: "active";
  renewalDate: Date;
}

interface PastDueSubscription extends SubscriptionBase {
  status: "past_due";
  retryCount: number;
  gracePeriodEnd: Date;
}

interface CanceledSubscription extends SubscriptionBase {
  status: "canceled";
  cancelReason: string;
  voluntary: boolean;
}

type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;
```

The `status` field is the discriminant. TypeScript narrows on it automatically:

```typescript
function describe(sub: Subscription): string {
  switch (sub.status) {
    case "trialing":
      return `trial ends ${sub.trialEndDate.toDateString()}`;
    case "active":
      return `renews ${sub.renewalDate.toDateString()}`;
    case "past_due":
      return `retry ${sub.retryCount}, grace ends ${sub.gracePeriodEnd.toDateString()}`;
    case "canceled":
      return sub.voluntary ? `canceled: ${sub.cancelReason}` : `involuntary: ${sub.cancelReason}`;
    default:
      return assertNever(sub);
  }
}

function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}
```

`assertNever` is the exhaustiveness device — the fourth rung on the ladder (make completeness checkable). Add a `paused` variant to the union later, and this `switch` fails to compile everywhere it's missing, instead of quietly hitting `default`.

★ Insight ─────────────────────────────────────
`sub.cancelReason` only type-checks inside the `"canceled"` branch — outside a narrowed branch, TypeScript won't even let you *ask* for it, because the compiler doesn't know which member of the union you're holding. That's the mechanism that makes the illegal state (e.g. reading a cancel reason off an active sub) not just "wrong" but literally uncompilable, versus a single-shape type where it'd type-check fine and blow up at runtime as `undefined`.
─────────────────────────────────────────────────

**What this doesn't cover, on purpose**: it says nothing about which transitions are legal (can `past_due` go straight to `trialing`? can a `canceled` sub reactivate?). That's state-machine logic, not a type-shape problem — a `transition(current, event)` function belongs on top of this. I didn't stub it because in a real app that's a business-logic call only you can make correctly (e.g., does an involuntary-canceled sub ever get retried?).

**Your turn**: in `subscription.ts`, sketch what `type SubscriptionEvent` looks like and which `(status, event) → status` pairs are legal — that's the part that encodes your actual retry/dunning policy, not a generic pattern. Once you have the event shapes, a `transition()` function with an exhaustive switch is trivial to add.