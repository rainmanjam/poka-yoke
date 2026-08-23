Using **poka-yoke:design** to shape this — a state-dependent record like this is exactly what discriminated unions exist for.

**Misuse enumeration first** (per the skill's ritual):
1. Same-shape fields (`trialEndsAt`, `graceEndsAt`, `renewsAt` are all dates) sitting on one flat object with everything optional would let you construct `{status: "active", retryCount: 3, cancelReason: "..."}` — nonsense, but the compiler wouldn't blink.
2. A caller must remember "only read `retryCount` when `status === 'past_due'`" — that's a rung-zero mental rule if the type doesn't enforce it.
3. Exactly 4 states, each with genuinely different payload → textbook discriminated union, not a bag of optionals.
4. Next year someone adds `"paused"` — the win condition is "the build breaks everywhere that needs updating," not "it silently falls into the `active` branch."

Here's the shape:

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

type SubscriptionId = Brand<string, "SubscriptionId">;
type CustomerId = Brand<string, "CustomerId">;

interface SubscriptionBase {
  id: SubscriptionId;
  customerId: CustomerId;
}

export type Subscription =
  | (SubscriptionBase & {
      status: "trialing";
      trialEndsAt: Date;
    })
  | (SubscriptionBase & {
      status: "active";
      renewsAt: Date;
    })
  | (SubscriptionBase & {
      status: "past_due";
      retryCount: number;
      graceEndsAt: Date;
    })
  | (SubscriptionBase & {
      status: "canceled";
      cancelReason: string;
      voluntary: boolean;
    });

function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

// Compiler forces every case, and a new status breaks the build here first.
function describe(sub: Subscription): string {
  switch (sub.status) {
    case "trialing": return `trial ends ${sub.trialEndsAt.toISOString()}`;
    case "active":   return `renews ${sub.renewsAt.toISOString()}`;
    case "past_due": return `retry ${sub.retryCount}, grace ends ${sub.graceEndsAt.toISOString()}`;
    case "canceled": return `canceled (${sub.voluntary ? "voluntary" : "involuntary"}): ${sub.cancelReason}`;
    default:         return assertNever(sub);
  }
}
```

★ Insight ─────────────────────────────────────
`sub.retryCount` is literally inaccessible until you've narrowed `sub.status === "past_due"` — TypeScript won't let you read it in the `active` branch. That's the difference between "please remember to check status first" (a comment) and the compiler refusing to compile the mistake (Control rung).
The `assertNever` in the `default` case is what makes adding `"paused"` next year a build failure at every switch that needs updating, rather than something silently falling through to `describe`'s last branch.
`SubscriptionId`/`CustomerId` are branded strings — costs nothing at runtime, but `updateSub(customerId, subscriptionId)` with swapped args is now a compile error instead of a support ticket.
─────────────────────────────────────────────────

**What I left possible, deliberately:** this type says nothing about which transitions are legal (can `canceled` go back to `active`? does `past_due` always come from `active`, or can a trial fail payment directly?). That's a motion-step device (a transition function with a lookup table of legal `from → to` pairs), and it's genuinely your call, not mine — it depends on how your billing provider's webhooks actually fire.

If you want that guarded too, here's where it plugs in — this is a good one for you to write since it encodes a business rule I can't guess correctly:

```ts
// TODO(you): fill in the legal transition table. Illegal pairs should be
// unrepresentable at the call site, not just checked-and-thrown — e.g. should
// "trialing -> canceled" require a cancelReason but "active -> canceled" too?
function transition(current: Subscription["status"], next: Subscription["status"]): boolean {
  // ...
}
```

Also worth flagging: this type has no runtime enforcement — if these records come off a Stripe webhook or a DB row, parse them into this shape with a Zod discriminated union at that boundary rather than casting, or the whole exercise buys you nothing past the parse point. Want me to sketch that parser too?