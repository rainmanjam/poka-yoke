Good — no existing subscription types in this repo to build on, so this is a fresh design. Enumerating misuse first (per poka-yoke:design): the biggest hazard here is a flat `{status, trialEndsAt?, renewalDate?, retryCount?, graceEndsAt?, cancelReason?, voluntary?}` shape — with 4 states and ~5 optional fields, the type claims dozens of legal combinations when only 4 are real (e.g. `active` with a `cancelReason` set, or `trialing` with no `trialEndsAt`). A discriminated union kills that at the type level instead of relying on someone remembering to check `status` before reading the right field.

```typescript
type SubscriptionId = string & { readonly __brand: 'SubscriptionId' };

interface SubscriptionBase {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
}

type Subscription =
  | (SubscriptionBase & {
      status: 'trialing';
      trialEndsAt: Date;
    })
  | (SubscriptionBase & {
      status: 'active';
      renewsAt: Date;
    })
  | (SubscriptionBase & {
      status: 'past_due';
      retryCount: number;
      graceEndsAt: Date;
    })
  | (SubscriptionBase & {
      status: 'canceled';
      canceledAt: Date;
    } & CancelDetails);

// "voluntary or not" isn't a boolean bolted onto one reason field — it's its own
// fork, because the two cases have genuinely different reason vocabularies.
type CancelDetails =
  | { voluntary: true; reason: VoluntaryCancelReason }
  | { voluntary: false; reason: InvoluntaryCancelReason };
```

`★ Insight ─────────────────────────────────────`
- Nesting `CancelDetails` as its own union (rather than `reason: string; voluntary: boolean`) means a voluntary cancellation literally cannot be paired with an involuntary reason like `payment_failed` — the compiler rejects it, no runtime check needed.
- `SubscriptionId` is branded (`string & {__brand}`) so it can't be passed where a `CustomerId` is expected even though both are strings underneath — the classic same-type-adjacent-to-same-type swap from the design ritual.
- Narrowing on `status` in a `switch` gives you full field access with no optional-chaining — `sub.retryCount` is just there once TS knows `sub.status === 'past_due'`.
`─────────────────────────────────────────────────`

One more device worth adding — exhaustiveness so a 5th status can't sneak in silently:

```typescript
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

function describe(sub: Subscription): string {
  switch (sub.status) {
    case 'trialing': return `trial ends ${sub.trialEndsAt.toISOString()}`;
    case 'active': return `renews ${sub.renewsAt.toISOString()}`;
    case 'past_due': return `retry ${sub.retryCount}, grace ends ${sub.graceEndsAt.toISOString()}`;
    case 'canceled': return sub.voluntary ? `canceled: ${sub.reason}` : `lost: ${sub.reason}`;
    default: return assertNever(sub);
  }
}
```

The one thing I deliberately left open: the actual reason vocabularies. That's a business call, not a type-design call — in `Subscription.ts`, add:

```typescript
type VoluntaryCancelReason = 'too_expensive' | /* your other reasons */;
type InvoluntaryCancelReason = 'payment_failed' | /* your other reasons */;
```

What reasons does your team actually track today (support tickets, exit survey, dunning exhaustion)? That list drives what analytics/dunning code can branch on later, so it's worth getting right now rather than guessing.