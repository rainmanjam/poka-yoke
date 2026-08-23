Here's the misuse list I'd check before writing the shape, then the types.

**What could go wrong with a flatter design** (e.g. one interface with `trialEndsAt?`, `retryCount?`, `graceEndsAt?`, `cancelReason?`, `voluntary?`, `renewsAt?` all optional):
- All 4 status-specific fields become optional, so nothing stops `{status: 'active', cancelReason: 'too_expensive'}` from compiling — an active sub with a cancellation reason, or a `past_due` with no `graceEndsAt` at all.
- A `switch` on `status` that forgets the `past_due` branch just silently falls through instead of failing the build.
- `voluntary` and `cancelReason` travel together but nothing ties them — a system-triggered churn (`payment_failed`) could get `voluntary: true` by a copy-paste mistake.

**The fix is rung 1 — make the illegal combinations unrepresentable with a discriminated union:**

```typescript
// --- branding: an id is not just a string ---
type SubscriptionId = string & { readonly __brand: 'SubscriptionId' };
type CustomerId = string & { readonly __brand: 'CustomerId' };

// --- cancellation reasons diverge by path, so give them their own union ---
type Cancellation =
  | { voluntary: true; reason: 'too_expensive' | 'missing_features' | 'switched_provider' | 'no_longer_needed' }
  | { voluntary: false; reason: 'payment_failed' | 'fraud_review' | 'chargeback' };

interface SubscriptionBase {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
}

type Subscription =
  | (SubscriptionBase & { status: 'trialing'; trialEndsAt: Date })
  | (SubscriptionBase & { status: 'active'; renewsAt: Date })
  | (SubscriptionBase & { status: 'past_due'; retryCount: number; graceEndsAt: Date })
  | (SubscriptionBase & ({ status: 'canceled' } & Cancellation));

// --- exhaustiveness: adding a 5th status breaks every switch that must handle it ---
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

function hasAccess(sub: Subscription): boolean {
  switch (sub.status) {
    case 'trialing':
    case 'active':
      return true;
    case 'past_due':
      return sub.graceEndsAt > new Date();
    case 'canceled':
      return false;
    default:
      return assertNever(sub);
  }
}
```

★ Insight ─────────────────────────────────────
- The `Cancellation` sub-union is the same move one level down: `voluntary` and `reason` aren't independent booleans-and-strings, they're two different *shapes* of the same concept (user decided vs. system decided), so splitting them means you can't stamp a payment-failure reason onto a voluntary cancellation.
- `assertNever` is what turns "I forgot to handle `past_due` in this one function" from a runtime surprise into a compile error — it costs one line per switch and is one of the highest-leverage devices in the list.
- Branding `SubscriptionId`/`CustomerId` as distinct string types stops `getSubscription(customerId)` from type-checking when the argument order gets swapped, which is the single most common footgun in code with several same-typed adjacent params.
─────────────────────────────────────────────────

What this design deliberately leaves open: **state transitions**. Nothing here stops calling code from constructing a `canceled` subscription directly out of a `trialing` one without going through your actual cancellation/dunning policy — TypeScript can express "this shape is legal" but not "this shape is reachable from that shape." That's the part only you know: does a trial that ends without a card go straight to `canceled`, or through `past_due` first? Can a `past_due` sub un-cancel back to `active` with a new `renewsAt`, or does recovery always require a fresh subscription?

That's genuinely your call to make, and it shapes the whole lifecycle. Want to sketch the transition function yourself? Something like:

```typescript
type SubscriptionEvent =
  | { type: 'TRIAL_ENDED'; paymentSucceeded: boolean }
  | { type: 'RENEWAL_SUCCEEDED' }
  | { type: 'RENEWAL_FAILED' }
  | { type: 'GRACE_PERIOD_EXPIRED' }
  | { type: 'CANCELED'; by: Cancellation };

// TODO(you): encode your actual dunning/lifecycle policy here.
// e.g. does TRIAL_ENDED with paymentSucceeded=false go to past_due or straight to canceled?
// does RENEWAL_FAILED reset retryCount or increment it?
function transition(current: Subscription, event: SubscriptionEvent): Subscription {
  throw new Error('not implemented');
}
```

Once you fill that in I can add the exhaustiveness check across `(status, event)` pairs so an illegal transition (e.g. `canceled` + `RENEWAL_SUCCEEDED`) is a type error rather than a runtime bug.