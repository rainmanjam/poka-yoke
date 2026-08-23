Using **poka-yoke:design** to shape the subscription type — this is exactly its case: a data model with four states, each carrying different required fields, about to be written before it has any callers.

**Misuse check first** (per the skill's ritual — two minutes, decides the design):

1. Bag-of-optionals hazard — if you model this as one interface with `trialEndDate?`, `retryCount?`, `cancelReason?` etc. all optional, you can construct a `canceled` subscription that also carries a `renewalDate`, or an `active` one with a `retryCount`. Nonsense states become representable.
2. ID swap — `subscriptionId` and `customerId` are both strings; nothing stops passing one where the other belongs.
3. "Must remember" — a caller reading `sub.trialEndsAt` must remember to check `status === "trialing"` first. If that's just a plain optional, TypeScript won't force the check.
4. New case next year — if you add a `paused` status, does every `switch` over status fail to compile until handled, or does it silently fall through?

That maps directly onto **discriminated unions** (contact lens) plus **branded IDs** (contact lens) plus **exhaustive switch** (fixed-value lens), which is exactly what `references/lang-typescript.md` prescribes for this shape.

```typescript
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId = Brand<string, "CustomerId">;

export const SubscriptionId = (s: string): SubscriptionId => s as SubscriptionId;
export const CustomerId = (s: string): CustomerId => s as CustomerId;

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
      cancelReason: CancelReason;
    });

// TODO(you): fill in the real reason codes for your product.
// This is a business decision, not a types decision — I don't know what
// counts as a voluntary vs. involuntary cancellation in your billing flow
// (e.g. is a downgrade-to-zero a cancel? does a chargeback count as
// involuntary or its own status?). Modeling it as a discriminated union
// on `voluntary` means a reason code can never be attached to the wrong
// side — e.g. "chargeback" can't accidentally get voluntary: true.
export type CancelReason =
  | { voluntary: true; reason: /* your voluntary reason codes */ string }
  | { voluntary: false; reason: /* your involuntary reason codes */ string };

function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

// Every call site that branches on status is forced to handle a new
// variant at compile time — this is the payoff of the union.
export function describe(sub: Subscription): string {
  switch (sub.status) {
    case "trialing": return `trial ends ${sub.trialEndsAt.toISOString()}`;
    case "active": return `renews ${sub.renewsAt.toISOString()}`;
    case "past_due": return `retry ${sub.retryCount}, grace until ${sub.graceEndsAt.toISOString()}`;
    case "canceled": return `canceled, voluntary=${sub.cancelReason.voluntary}`;
    default: return assertNever(sub);
  }
}
```

**What this makes impossible (rung 1, Control):**
- A `canceled` subscription can no longer carry `renewsAt` or `retryCount` — TypeScript won't let those fields exist outside their variant, so `sub.trialEndsAt` is a compile error unless you've already narrowed `sub.status === "trialing"`.
- Swapping `SubscriptionId` and `CustomerId` at a call site is a compile error, not a runtime surprise.
- Adding a fifth status later breaks every `switch` that doesn't handle it, *if* you add `@typescript-eslint/switch-exhaustiveness-check` to your lint config — worth doing now while there's only one switch to fix.

**What I deliberately left open:** the union doesn't stop you from constructing a `Subscription` with `status: "active"` for something that was `canceled` yesterday — i.e. it says nothing about *legal transitions* (can `past_due` go straight to `trialing`? can `canceled` be reactivated?). That's a motion-step concern (typestate / a `transition()` function with an exhaustive from→to table), and it's worth doing once you've nailed down the actual transition rules — happy to build that next if useful.

★ Insight ─────────────────────────────────────
The `SubscriptionBase & { status: "trialing"; ... }` pattern works because TypeScript narrows on a **literal-typed discriminant field** — once you check `status === "trialing"` in a branch or switch case, the compiler eliminates the other union members entirely, so `trialEndsAt` becomes accessible without a null check. This only works if `status` is a string literal type, not `string` — the union falls apart silently if someone widens it.
─────────────────────────────────────────────────

Want me to write this to a file in your SaaS repo, or add the Zod schema for parsing it at the API boundary (so an untrusted payload can't be cast into a `Subscription` without validation)?