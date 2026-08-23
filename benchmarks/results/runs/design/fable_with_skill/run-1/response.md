Routed to `design` (it's "what should the types look like" for a state machine). Here's the design, with the misuse list first, as the skill prescribes.

**Misuses enumerated**
1. Bag of optionals: `{status, trialEndsAt?, retryCount?, gracePeriodEndsAt?, cancelReason?, voluntary?, renewsAt?}` claims 2⁷ states; 4 are real. A `past_due` row with no grace-period end becomes reachable (C8).
2. `status: string` — typos compile; a 5th status added next year silently falls into `default` (C4, F1).
3. Status mutated by assignment from webhooks, cron, and admin UI — `canceled → active` becomes sayable (M3).
4. Two adjacent dates/numbers swap silently; `retryCount` drifts negative (C1, C5).
5. Dates arrive as strings from Stripe/the DB and get compared unparsed (C9, C7).

**The types**

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId     = Brand<string, "CustomerId">;
export type Instant        = Brand<Date, "Instant">;      // UTC, parsed at the boundary
export type RetryCount     = Brand<number, "RetryCount">; // non-negative int, parsed

interface Base {
  readonly id: SubscriptionId;
  readonly customerId: CustomerId;
}

export type Subscription =
  | (Base & { readonly status: "trialing"; readonly trialEndsAt: Instant })
  | (Base & { readonly status: "active";   readonly renewsAt: Instant })
  | (Base & { readonly status: "past_due"; readonly retryCount: RetryCount; readonly gracePeriodEndsAt: Instant })
  | (Base & { readonly status: "canceled"; readonly reason: CancelReason; readonly voluntary: boolean });

export type CancelReason = "user_requested" | "payment_failed" | "fraud" | "downgraded";
```

Every per-status field is *required* on its variant and *absent* from the others — `sub.retryCount` doesn't typecheck until you've narrowed to `past_due`.

**The only door into a new state** — a single transition function, exhaustively matched:

```ts
function assertNever(x: never): never { throw new Error(`Unhandled: ${JSON.stringify(x)}`); }

export type Event =
  | { type: "trial_converted"; renewsAt: Instant }
  | { type: "payment_failed";  gracePeriodEndsAt: Instant }
  | { type: "payment_recovered"; renewsAt: Instant }
  | { type: "canceled"; reason: CancelReason; voluntary: boolean };

export function transition(sub: Subscription, ev: Event): Subscription {
  switch (sub.status) {
    case "trialing":
      if (ev.type === "trial_converted") return { ...base(sub), status: "active", renewsAt: ev.renewsAt };
      if (ev.type === "canceled")        return { ...base(sub), status: "canceled", reason: ev.reason, voluntary: ev.voluntary };
      throw new IllegalTransition(sub.status, ev.type);
    case "active":      /* payment_failed → past_due(retryCount 0) · canceled */
    case "past_due":    /* payment_failed → retryCount+1 · payment_recovered → active · canceled */
    case "canceled":    throw new IllegalTransition(sub.status, ev.type);   // terminal
    default:            return assertNever(sub);
  }
}
```

**Rungs reached**
- Nonsense field combinations: **Control** (union) — no spelling for it.
- Unhandled new status: **Control** (`assertNever` + `switch-exhaustiveness-check` lint).
- Illegal transition (`canceled → active`): **Warning** (throws). Control would need typestate (`Trialing`, `Active`... classes with only legal methods); I didn't take it because ORM hydration returns one type per table row, and typestate fights that hard.
- Swapped dates / bad input: **Control** via brands, but *only* if `Instant`/`RetryCount` are minted exclusively by a zod parser at the webhook and DB edges — an `as` cast anywhere else reduces this to a comment.

**Consciously left possible**: `voluntary: boolean` alongside `reason` — `{reason: "fraud", voluntary: true}` is representable. If that combination is truly nonsense, fold it in: `reason: "user_requested" | "downgraded"` ⇒ voluntary, the rest ⇒ involuntary, derive `voluntary` rather than store it. That's a domain call for you.

**Push one device to the DB**: a `CHECK` per status (`status <> 'past_due' OR (retry_count IS NOT NULL AND grace_period_ends_at IS NOT NULL)`) so a script with `psql` can't write the bag-of-optionals the type forbids. Note the catalog's caveat: a `CHECK` can't police *transitions*, only shapes — transitions stay in `transition()`.

`★ Insight ─────────────────────────────────────`
The union and `transition()` are one device split in two: the union makes the wrong *state* unsayable (contact lens), the exhaustive switch makes a *missing case* a build break (fixed-value lens). Adding `"paused"` next year fails to compile at exactly the sites that must change — that's the whole point.
`─────────────────────────────────────────────────`

Prerequisite for any of this to be load-bearing: `strict: true`, `exactOptionalPropertyTypes`, and `tsc --noEmit` as a required CI check.