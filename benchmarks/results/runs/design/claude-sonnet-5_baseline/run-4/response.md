## Misuse enumerated

- **Bag-of-optionals trap**: a `{status, trialEndsAt?, renewalDate?, retryCount?, graceEndsAt?, cancelReason?, voluntary?}` shape lets you construct a "canceled" sub that still carries a `retryCount`, or an "active" one with a `cancelReason`. Nothing stops it at compile time — it's caught (if at all) by a runtime check someone has to remember to write.
- **Swap risk**: `trialEndsAt`, `renewalDate`, `graceEndsAt` are all `Date`, same type, easy to wire to the wrong field if they lived on one flat object. A discriminated union makes that impossible — each field only exists on the variant it belongs to.
- **Exhaustiveness**: when you add `paused` next year, every `switch` over status needs to handle it. Left to prose ("remember to update the renewal job"), it won't happen everywhere.
- **`voluntary: boolean` + free-text `reason: string`**: nothing stops `{voluntary: true, reason: "payment_failed"}` (an involuntary reason mislabeled voluntary) or a typo'd reason string that silently fails to match your churn dashboard's grouping logic.

## Design

```typescript
type SubscriptionId = string & { readonly __brand: "SubscriptionId" };

interface SubscriptionBase {
  id: SubscriptionId;
}

interface TrialingSubscription extends SubscriptionBase {
  status: "trialing";
  trialEndsAt: Date;
}

interface ActiveSubscription extends SubscriptionBase {
  status: "active";
  renewsAt: Date;
}

interface PastDueSubscription extends SubscriptionBase {
  status: "past_due";
  retryCount: number;
  graceEndsAt: Date;
}

type CanceledSubscription = SubscriptionBase & { status: "canceled" } & (
  | { voluntary: true; reason: VoluntaryCancelReason }
  | { voluntary: false; reason: InvoluntaryCancelReason }
);

type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;

function assertNever(x: never): never {
  throw new Error(`Unhandled subscription variant: ${JSON.stringify(x)}`);
}

function nextActionFor(sub: Subscription): string {
  switch (sub.status) {
    case "trialing":
      return `convert or expire by ${sub.trialEndsAt.toISOString()}`;
    case "active":
      return `renew ${sub.renewsAt.toISOString()}`;
    case "past_due":
      return `retry #${sub.retryCount}, grace ends ${sub.graceEndsAt.toISOString()}`;
    case "canceled":
      return sub.voluntary ? `voluntary: ${sub.reason}` : `involuntary: ${sub.reason}`;
    default:
      return assertNever(sub);
  }
}
```

`★ Insight ─────────────────────────────────────`
- The outer union is keyed on `status`; the cancellation branch nests a *second* discriminated union on `voluntary`. That's the same device applied one level deeper — it stops "voluntary cancel with an involuntary-only reason code" from compiling, the exact bug a flat `{voluntary, reason: string}` shape allows.
- `SubscriptionId` is branded (`string & {__brand}`) rather than a bare `string`, so `getSubscription(customerId)` (wrong ID type, right runtime type) is a type error, not a 2am bug.
- `assertNever` in the `default` arm is what makes the switch a *device* instead of documentation — add `paused` to the union and every unhandled switch fails the build, not silently falls through to `undefined`.
`─────────────────────────────────────────────────`

One thing left for you: the actual reason codes. I stubbed `VoluntaryCancelReason` / `InvoluntaryCancelReason` as named types but didn't fill them in — that's your churn taxonomy, not mine to guess. In whatever file holds this, write the 5-10 lines yourself, e.g.:

```typescript
type VoluntaryCancelReason =
  | "too_expensive"
  | "missing_features"
  | "switched_competitor"
  | "no_longer_needed"
  | "other";

type InvoluntaryCancelReason =
  | "payment_failed"
  | "fraud_flagged"
  | "chargeback";
```

Whatever values you pick here become the labels on your churn dashboard, so worth getting them to match how the business actually talks about cancellations rather than what's technically convenient.

**Left possible on purpose**: nothing stops constructing a `Subscription` object literal directly (bypassing any invariant-checking constructor) — fine for a pure domain type, but if these get built from raw DB rows or Stripe webhooks, put a `parseSubscription(raw: unknown): Subscription` at that boundary rather than trusting `as Subscription` casts scattered through the codebase.