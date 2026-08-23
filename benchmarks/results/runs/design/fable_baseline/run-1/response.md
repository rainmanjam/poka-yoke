Here's the shape I'd use. The core move: **a discriminated union on `status`**, so each state carries exactly its own fields and nothing else.

```ts
// --- Branded primitives: stop swapping IDs / dates / counts -------------------
type Brand<T, B extends string> = T & { readonly __brand: B };
export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId     = Brand<string, "CustomerId">;
export type PlanId         = Brand<string, "PlanId">;

// --- Fields every subscription has -------------------------------------------
interface SubscriptionBase {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
  readonly planId: PlanId;
  readonly createdAt: Date;
}

// --- One variant per state ---------------------------------------------------
export interface TrialingSubscription extends SubscriptionBase {
  readonly status: "trialing";
  readonly trialEndsAt: Date;
}

export interface ActiveSubscription extends SubscriptionBase {
  readonly status: "active";
  readonly renewsAt: Date;
}

export interface PastDueSubscription extends SubscriptionBase {
  readonly status: "past_due";
  readonly retryCount: number;        // see note below on bounding this
  readonly gracePeriodEndsAt: Date;
}

export type CancelReason =
  | "user_requested"
  | "payment_failed"
  | "fraud"
  | "plan_discontinued";

export interface CanceledSubscription extends SubscriptionBase {
  readonly status: "canceled";
  readonly canceledAt: Date;
  readonly reason: CancelReason;
  readonly voluntary: boolean;
}

export type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;

export type SubscriptionStatus = Subscription["status"];

// --- Exhaustiveness: adding a 5th state breaks the build everywhere ----------
export function assertNever(x: never): never {
  throw new Error(`Unhandled subscription state: ${JSON.stringify(x)}`);
}

export function hasAccess(sub: Subscription, now: Date): boolean {
  switch (sub.status) {
    case "trialing": return now < sub.trialEndsAt;
    case "active":   return true;
    case "past_due": return now < sub.gracePeriodEndsAt;
    case "canceled": return false;
    default:         return assertNever(sub);
  }
}
```

★ Insight ─────────────────────────────────────
- A flat `{status, trialEndsAt?, retryCount?, reason?, ...}` claims 2⁶ = 64 legal states; only 4 exist. The union makes "active with a cancel reason" a compile error instead of a 3am mystery.
- `Subscription["status"]` derives the status enum from the union, so the two can never drift.
- The `default: assertNever(sub)` arm is the cheapest high-leverage device here: when you add `paused` next year, every `switch` that forgot it goes red.
─────────────────────────────────────────────────

**Misuse I enumerated and what this closes:**
- *Nonsense state combos* — closed, rung 1 (union).
- *Swapping `customerId`/`planId`/`subscriptionId`* — closed, rung 1 (brands). Dates are all `Date`, so `trialEndsAt`/`renewsAt` are distinguished by living in different variants, not by type.
- *Missing a case when a state is added* — closed, rung 4 (`assertNever`).
- *Mutating status in place* (`sub.status = "active"` leaving `trialEndsAt` dangling) — closed by `readonly`; transitions should be functions returning a new variant, e.g. `activate(sub: TrialingSubscription, renewsAt: Date): ActiveSubscription`. That signature also makes illegal transitions (canceled → active) unsayable.

**Left possible, on purpose:**
- `retryCount: number` can be negative or 1e9. I'd bound it at the parse boundary (`parseSubscription(row): Subscription`) rather than brand it — a newtype for one counter is past the point of paying.
- `reason` vs `voluntary` can contradict (`"fraud"` + `voluntary: true`). If `voluntary` is fully derivable from `reason`, drop it and compute it; if it isn't, this is a real product decision and worth your input — see below.

**One decision I'd hand to you:** is `voluntary` derivable from `reason`? If yes, replace the field with `isVoluntary(reason: CancelReason): boolean` and the contradiction vanishes. If no (e.g. `user_requested` can be involuntary when support cancels on the user's behalf), keep both but consider a nested union: `cancellation: { kind: "voluntary"; reason: ... } | { kind: "involuntary"; reason: ... }` with different reason sets per arm. That's the 5-line choice that shapes churn reporting, so it's worth you making it.

Also: persist `status` as a DB `CHECK` constraint and make the per-state columns `NOT NULL` via partial constraints if you're on Postgres — that keeps the invariant when someone writes a migration script outside TypeScript.