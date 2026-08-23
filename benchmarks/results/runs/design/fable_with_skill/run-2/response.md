Routed via `poka-yoke` → `design` (the ask is "what should the types look like" for a new interface). Misuse enumeration first, then the types.

**Misuses enumerated**
1. *Bag of optionals*: `{status, trialEndsAt?, retryCount?, graceEndsAt?, cancelReason?, voluntary?, renewsAt?}` claims 2⁵ states; you have 4.
2. *Illegal transitions*: `canceled → active` by assignment from anywhere.
3. *Swappable fields*: `trialEndsAt`/`graceEndsAt`/`renewsAt` are all `Date` — same-type adjacency.
4. *New status next year* (`paused`): should break the build, not fall through.
5. *Boundary*: rows from the DB / Stripe webhooks arrive as `any`.

```ts
// subscription.ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId     = Brand<string, "CustomerId">;

// Discriminated union — exactly four states have a spelling.
type Base = { readonly id: SubscriptionId; readonly customerId: CustomerId };

export type Subscription =
  | (Base & { readonly status: "trialing"; readonly trialEndsAt: Date })
  | (Base & { readonly status: "active";   readonly renewsAt: Date })
  | (Base & { readonly status: "past_due"; readonly retryCount: number; readonly graceEndsAt: Date })
  | (Base & { readonly status: "canceled"; readonly reason: CancelReason; readonly voluntary: boolean });

// Closed set, not a free string — typos don't compile, and tells you when a new reason needs handling.
export type CancelReason = "user_requested" | "payment_failed" | "fraud" | "downgraded";

export function assertNever(x: never): never {
  throw new Error(`Unhandled subscription variant: ${JSON.stringify(x)}`);
}
```

Then the motion-step device — **one** function is the only way a status changes:

```ts
export type Transition =
  | { readonly to: "active";   readonly renewsAt: Date }
  | { readonly to: "past_due"; readonly graceEndsAt: Date }
  | { readonly to: "canceled"; readonly reason: CancelReason; readonly voluntary: boolean };
  // note: no transition *to* "trialing" — trials only begin at creation.

export function transition(sub: Subscription, t: Transition): Subscription {
  switch (sub.status) {
    case "trialing":
    case "active":
    case "past_due":
      return apply(sub, t);
    case "canceled":
      throw new Error(`Illegal transition: canceled → ${t.to} (${sub.id})`);
    default:
      return assertNever(sub);
  }
}
```

`★ Insight ─────────────────────────────────────`
- `past_due → active` with a `retryCount` carried along? It can't be: the `active` variant has no `retryCount` field, so the stale counter is structurally dropped. The union does the cleanup for you.
- `retryCount: number` permits `-3` and `2.5`. Control would need a branded `NonNegativeInt` produced by a parser; I left that at rung 0 because the plausible bug (off-by-one) isn't caught by branding either. Put `CHECK (retry_count >= 0)` in the schema instead — that's Control and it survives `psql`.
`─────────────────────────────────────────────────`

**Rungs reached / consciously left open**
- Impossible states, swapped dates, unhandled new status → **Control** (union + `assertNever`; enable `@typescript-eslint/switch-exhaustiveness-check`).
- `canceled → anything` → **Control** at the `transition` gate — but only if `transition` is the sole writer. Types vanish at runtime, so back it with a DB `CHECK` on per-status column nullability, and a trigger if you want the *transition* policed there (a row CHECK can't see the prior state).
- Boundary: parse DB rows / Stripe events through a zod schema of this union so `any` never reaches `transition`. Not shown; it's mechanical.

**Your call — the `apply` body.** Which transitions are legal is business logic, not type design: does `trialing → past_due` exist (card failed at trial end), or does a failed trial go straight to `canceled` with `voluntary: false`? Can `past_due` re-enter `past_due` (retry increments count)? Write `apply(sub, t)` as a `switch` on `\`${sub.status}→${t.to}\`` with `assertNever` on the default, and every combination you didn't list becomes a compile error rather than a silent no-op.

Recap: discriminated union for the four states, branded IDs, a closed `CancelReason`, and a single `transition` function with exhaustive matching. Left open by choice: `retryCount` bounds (push to DB `CHECK`) and the legal-transition table, which is yours to define.