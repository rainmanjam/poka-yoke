This repo is the poka-yoke skills repo, not your SaaS — no TS project here, so I'll give you the design inline and drop it into a file once you tell me the path.

## Misuse enumeration first

Running the design skill's ritual on your four states:

1. **Swappable params** — `subscriptionId`, `customerId`, `planId` are all `string`. Any two can be transposed silently.
2. **Nonsense states** — the naive shape (`status` + 5 optional fields) claims 2^5 = 32 states. Four exist. `{status: 'active', cancelReason: 'too expensive', retryCount: 3}` type-checks.
3. **"Whether it was voluntary"** — a `boolean` beside a free-text `reason` is a second bag of optionals hiding inside the canceled case. The *reason set differs* by voluntariness: "too expensive" and "card declined after 4 retries" are not the same field.
4. **New case next year** — Stripe alone has `paused`, `incomplete`, `unpaid`. Adding one should break the build, not fall through.

## The types

```ts
// ── Branded IDs (rung 1: distinct types for distinct concepts) ──
declare const brand: unique symbol;
type Brand<T, B extends string> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, 'SubscriptionId'>;
export type CustomerId     = Brand<string, 'CustomerId'>;
export type PlanId         = Brand<string, 'PlanId'>;

// ── Fields true in every state ──
interface SubscriptionCore {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
  readonly planId: PlanId;
  readonly startedAt: Date;
}

// ── Cancellation: nested union, not boolean + string ──
export type Cancellation =
  | { readonly kind: 'voluntary';   readonly reason: VoluntaryReason }
  | { readonly kind: 'involuntary'; readonly reason: InvoluntaryReason };

export type VoluntaryReason =
  | 'too_expensive' | 'missing_features' | 'switched_provider' | 'no_longer_needed';

export type InvoluntaryReason =
  | 'payment_failed' | 'fraud' | 'terms_violation';

// ── The four states ──
export interface TrialingSubscription extends SubscriptionCore {
  readonly status: 'trialing';
  readonly trialEndsAt: Date;
}

export interface ActiveSubscription extends SubscriptionCore {
  readonly status: 'active';
  readonly renewsAt: Date;
}

export interface PastDueSubscription extends SubscriptionCore {
  readonly status: 'past_due';
  readonly retryCount: number;
  readonly gracePeriodEndsAt: Date;
  readonly firstFailedAt: Date;
}

export interface CanceledSubscription extends SubscriptionCore {
  readonly status: 'canceled';
  readonly canceledAt: Date;
  readonly cancellation: Cancellation;
}

export type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;

export type SubscriptionStatus = Subscription['status'];
```

★ Insight ─────────────────────────────────────
- `SubscriptionStatus` is *derived* from the union, not declared alongside it. Declaring both lets them drift; deriving means adding a state to the union automatically widens the status type.
- `Cancellation` as a nested union is the move most people miss. `voluntary: boolean` + `reason: string` permits `{voluntary: true, reason: 'fraud'}` — nonsense that reads fine in a code review.
- Branding via `unique symbol` means `SubscriptionId` erases to `string` at runtime (zero cost) but a raw string won't assign to it without an explicit parse.
─────────────────────────────────────────────────

## The exhaustiveness device

This is the line that makes next year's new state a build failure:

```ts
export function assertNever(x: never): never {
  throw new Error(`Unhandled subscription state: ${JSON.stringify(x)}`);
}

// Every consumer follows this shape:
export function describeAccess(sub: Subscription): string {
  switch (sub.status) {
    case 'trialing': return `Trial ends ${sub.trialEndsAt.toISOString()}`;
    case 'active':   return `Renews ${sub.renewsAt.toISOString()}`;
    case 'past_due': return `Grace until ${sub.gracePeriodEndsAt.toISOString()}`;
    case 'canceled': return `Canceled (${sub.cancellation.kind})`;
    default:         return assertNever(sub);
  }
}
```

Add `'paused'` to the union and every `switch` missing an arm fails to compile. One line per switch, and it's the highest-leverage device in the file.

---

## What I'd like your input on

I've deliberately **not** written the transition function, because the legal-transition map is domain knowledge I'd be guessing at, and guessing wrong here is how subscriptions get resurrected or double-billed. The questions that actually decide it:

- **Can `canceled` → `active`?** If reactivation is a real product feature, canceled isn't terminal, and `canceledAt` needs to survive as history rather than be overwritten.
- **Can `past_due` → `trialing`?** Almost certainly not, but if you offer "win-back trials" it might be.
- **Does `trialing` → `past_due` exist**, or does a failed first charge go straight to `canceled`?

Once you answer those, the transition table becomes:

```ts
// TODO(you): fill this in — the compiler will then reject illegal transitions at
// every call site, not just in the function that applies them.
const LEGAL_TRANSITIONS: Record<SubscriptionStatus, readonly SubscriptionStatus[]> = {
  trialing: [/* ? */],
  active:   [/* ? */],
  past_due: [/* ? */],
  canceled: [/* ? */],
};
```

Tell me the three answers and the repo path, and I'll write the file with `parseSubscription` (parse-don't-validate at your Stripe webhook and DB boundaries) plus a `transition()` that makes illegal moves a type error rather than a runtime check.

One thing I left possible on purpose: `retryCount` is a plain `number`, so `-1` and `9999` are sayable. Worth a branded bounded type only if your dunning logic branches on the exact value — otherwise it's the "five wrapper types for one function" overreach the skill warns about.