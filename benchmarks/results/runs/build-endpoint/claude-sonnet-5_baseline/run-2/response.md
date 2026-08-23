## Misuse enumeration (per poka-yoke:design)

1. **Swappable params** — `orderId`/`reason` are adjacent strings. Zod parses them into a named object at the boundary, not positional args, so swapping is a type error, not a runtime bug.
2. **Must-remember** — caller must scope the order lookup to the caller's tenant. Nothing enforces this by convention; I make "wrong tenant" and "doesn't exist" the *same* code path so it's structurally impossible to leak existence across tenants.
3. **Nonsense states** — a `Refund` row could exist without Stripe actually having refunded anything (crash between the two writes). Fixed by only ever inserting the row *after* Stripe confirms, and making the whole flow replay-safe.
4. **Second call (the big one)** — retry/double-click double-refunds. Solved two ways: Stripe-side idempotency key on the API call, and DB-side unique constraint on `idempotencyKey` so a replayed request returns the original row instead of creating a second one.
5. **Worst input** — negative/zero amount, over-refund past the order total, refunding someone else's order. Amount is validated positive at the Zod boundary; over-refund is checked in the app for a fast error *and* enforced by a Postgres trigger that is the actual source of truth (survives races, other services, `psql`).
6. **New case next year** — refund reasons. Modeled as a closed union with an exhaustive `switch` mapping to Stripe's reason enum, so adding a reason without updating the mapping fails the build.

**Left possible, deliberately:** if the process crashes *after* Stripe confirms but *before* the DB insert, the row won't exist until the client retries with the same `Idempotency-Key` — there's no background reconciliation job here. That's a reasonable MVP tradeoff (Stripe is the source of truth, our row is just a mirror), but a real reconciliation sweep against Stripe's refund list would close the last gap.

★ Insight ─────────────────────────────────────
The `Order` schema you gave has no Stripe reference at all — no `stripePaymentIntentId`. Without it there's nothing to hand Stripe's `refunds.create` to know *what* to refund. I added it as a required schema addition, called out explicitly below rather than silently invented — this is the kind of gap that's easy to paper over with an "assume it exists" comment and then discover in prod.
─────────────────────────────────────────────────

---

### `prisma/schema.prisma` (additions)

```prisma
model Order {
  id                    String   @id @default(uuid())
  tenantId              String
  totalCents            Int
  currency              String
  // Added: without this there is nothing to pass to Stripe's refunds.create.
  stripePaymentIntentId String?  @unique
  refunds               Refund[]

  @@index([tenantId])
}

model Refund {
  id             String   @id @default(uuid())
  orderId        String
  order          Order    @relation(fields: [orderId], references: [id])
  amountCents    Int
  reason         String
  // Added: Stripe's refund id, so a crash-and-retry can be reconciled by hand if ever needed.
  stripeRefundId String   @unique
  // Added: required, not optional — an optional idempotency key is a suggestion.
  idempotencyKey String   @unique
  createdAt      DateTime @default(now())

  @@index([orderId])
}
```

### `prisma/migrations/20260822000000_add_refund_idempotency/migration.sql`

```sql
-- Order: link to the Stripe object refunds are actually issued against.
ALTER TABLE "Order" ADD COLUMN "stripePaymentIntentId" TEXT;
CREATE UNIQUE INDEX "Order_stripePaymentIntentId_key" ON "Order"("stripePaymentIntentId");

-- Refund: make retries safe and refunds traceable back to Stripe.
-- NOTE: if "Refund" already has rows in production, backfill stripeRefundId /
-- idempotencyKey for existing rows before running this as NOT NULL — shown here
-- as a clean addition, since this is a fresh environment.
ALTER TABLE "Refund" ADD COLUMN "stripeRefundId" TEXT NOT NULL;
ALTER TABLE "Refund" ADD COLUMN "idempotencyKey" TEXT NOT NULL;
CREATE UNIQUE INDEX "Refund_stripeRefundId_key" ON "Refund"("stripeRefundId");
CREATE UNIQUE INDEX "Refund_idempotencyKey_key" ON "Refund"("idempotencyKey");
CREATE INDEX "Refund_orderId_idx" ON "Refund"("orderId");

ALTER TABLE "Refund" ADD CONSTRAINT "Refund_amountCents_positive" CHECK ("amountCents" > 0);
ALTER TABLE "Refund" ADD CONSTRAINT "Refund_reason_known" CHECK (
  "reason" IN ('customer_request', 'duplicate_charge', 'fraudulent', 'order_cancelled', 'other')
);

-- Authoritative over-refund guard. Runs inside the same transaction as the
-- INSERT, and the FOR UPDATE lock on the Order row serializes concurrent
-- refund attempts against the same order — this is what actually prevents
-- the race that an app-level check alone cannot.
CREATE OR REPLACE FUNCTION enforce_refund_within_order_total()
RETURNS TRIGGER AS $$
DECLARE
  order_total INT;
  already_refunded INT;
BEGIN
  SELECT "totalCents" INTO order_total FROM "Order" WHERE id = NEW."orderId" FOR UPDATE;

  IF order_total IS NULL THEN
    RAISE EXCEPTION 'Refund references unknown order %', NEW."orderId";
  END IF;

  SELECT COALESCE(SUM("amountCents"), 0) INTO already_refunded
  FROM "Refund" WHERE "orderId" = NEW."orderId";

  IF already_refunded + NEW."amountCents" > order_total THEN
    RAISE EXCEPTION
      'Refund of % cents exceeds remaining balance for order % (already refunded % of % cents)',
      NEW."amountCents", NEW."orderId", already_refunded, order_total;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_refund_within_order_total
BEFORE INSERT ON "Refund"
FOR EACH ROW EXECUTE FUNCTION enforce_refund_within_order_total();
```

★ Insight ─────────────────────────────────────
The trigger, not the TypeScript `if (amountCents > remaining)` check, is what actually prevents an over-refund under concurrency. Two simultaneous requests can both read "remaining = $50" in the app layer before either writes — the app check alone has a TOCTOU race. `FOR UPDATE` inside the trigger forces the second transaction to wait for the first to commit (or roll back) before it can even read a consistent sum, so the second one correctly sees the reduced balance. The app-level check exists purely so honest callers get a fast, friendly 422 instead of a raw Postgres error on the unlucky race.
─────────────────────────────────────────────────

### `src/refunds/refund-reason.ts`

```typescript
import type Stripe from "stripe";

export const REFUND_REASONS = [
  "customer_request",
  "duplicate_charge",
  "fraudulent",
  "order_cancelled",
  "other",
] as const;

export type RefundReason = (typeof REFUND_REASONS)[number];

// Stripe only accepts 'duplicate' | 'fraudulent' | 'requested_by_customer'.
// Exhaustive switch: adding a RefundReason without extending this fails the build.
export function toStripeRefundReason(
  reason: RefundReason,
): Stripe.RefundCreateParams.Reason {
  switch (reason) {
    case "duplicate_charge":
      return "duplicate";
    case "fraudulent":
      return "fraudulent";
    case "customer_request":
    case "order_cancelled":
    case "other":
      return "requested_by_customer";
    default: {
      const unreachable: never = reason;
      throw new Error(`Unhandled refund reason: ${unreachable}`);
    }
  }
}
```

### `src/refunds/schema.ts`

```typescript
import { z } from "zod";
import { REFUND_REASONS } from "./refund-reason";

// Parse, don't validate: everything past this point works with a typed,
// already-checked CreateRefundRequest, never a raw request body.
export const CreateRefundRequestSchema = z.object({
  orderId: z.string().uuid(),
  amountCents: z.number().int().positive(),
  reason: z.enum(REFUND_REASONS),
});

export type CreateRefundRequest = z.infer<typeof CreateRefundRequestSchema>;
```

### `src/refunds/service.ts`

```typescript
import { Prisma, PrismaClient, Refund } from "@prisma/client";
import Stripe from "stripe";
import { CreateRefundRequest } from "./schema";
import { toStripeRefundReason } from "./refund-reason";

export class OrderNotFoundError extends Error {
  constructor(orderId: string) {
    super(`Order ${orderId} not found`);
  }
}

export class RefundExceedsBalanceError extends Error {}

export class MissingPaymentIntentError extends Error {
  constructor(orderId: string) {
    super(`Order ${orderId} has no Stripe payment intent on file`);
  }
}

export interface Session {
  userId: string;
  tenantId: string;
}

export async function createRefund(
  prisma: PrismaClient,
  stripe: Stripe,
  input: CreateRefundRequest,
  session: Session,
  idempotencyKey: string,
): Promise<Refund> {
  // Replay of an exact prior request: return what already happened instead
  // of re-executing anything.
  const existing = await prisma.refund.findUnique({ where: { idempotencyKey } });
  if (existing) return existing;

  // Tenant scoping happens in the query itself, not as a check afterward —
  // "not found" and "belongs to another tenant" are indistinguishable to the caller.
  const order = await prisma.order.findFirst({
    where: { id: input.orderId, tenantId: session.tenantId },
  });
  if (!order) throw new OrderNotFoundError(input.orderId);
  if (!order.stripePaymentIntentId) throw new MissingPaymentIntentError(order.id);

  const alreadyRefunded = await prisma.refund.aggregate({
    where: { orderId: order.id },
    _sum: { amountCents: true },
  });
  const remaining = order.totalCents - (alreadyRefunded._sum.amountCents ?? 0);
  if (input.amountCents > remaining) {
    // Fast-path rejection only. The enforce_refund_within_order_total trigger
    // is the real guarantee and holds even if this check races.
    throw new RefundExceedsBalanceError(
      `Requested ${input.amountCents}c exceeds remaining refundable balance of ${remaining}c`,
    );
  }

  // Stripe's own idempotency key means a retry after a crash here (e.g. we
  // never reach the DB insert below) replays the same refund instead of
  // charging twice.
  const stripeRefund = await stripe.refunds.create(
    {
      payment_intent: order.stripePaymentIntentId,
      amount: input.amountCents,
      reason: toStripeRefundReason(input.reason),
      metadata: {
        orderId: order.id,
        tenantId: session.tenantId,
        requestedByUserId: session.userId,
      },
    },
    { idempotencyKey },
  );

  try {
    return await prisma.refund.create({
      data: {
        orderId: order.id,
        amountCents: input.amountCents,
        reason: input.reason,
        stripeRefundId: stripeRefund.id,
        idempotencyKey,
      },
    });
  } catch (err) {
    if (err instanceof Prisma.PrismaClientKnownRequestError && err.code === "P2002") {
      // Lost a race with a concurrent identical retry — Stripe already
      // deduplicated the money movement, so just return the winning row.
      const winner = await prisma.refund.findUnique({ where: { idempotencyKey } });
      if (winner) return winner;
    }
    throw err;
  }
}
```

### `src/refunds/route.ts`

```typescript
import { Router } from "express";
import { CreateRefundRequestSchema } from "./schema";
import {
  createRefund,
  OrderNotFoundError,
  RefundExceedsBalanceError,
  MissingPaymentIntentError,
  Session,
} from "./service";
import { prisma } from "../db";
import { stripe } from "../stripe";

export const refundsRouter = Router();

refundsRouter.post("/refunds", async (req, res, next) => {
  // Set by upstream auth middleware — never trust these from the request body.
  const session = req.session as Session;

  const idempotencyKey = req.header("Idempotency-Key");
  if (!idempotencyKey) {
    return res.status(400).json({ error: "Idempotency-Key header is required" });
  }

  const parsed = CreateRefundRequestSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: parsed.error.flatten() });
  }

  try {
    const refund = await createRefund(prisma, stripe, parsed.data, session, idempotencyKey);
    return res.status(201).json(refund);
  } catch (err) {
    if (err instanceof OrderNotFoundError) {
      return res.status(404).json({ error: "Order not found" });
    }
    if (err instanceof RefundExceedsBalanceError) {
      return res.status(422).json({ error: err.message });
    }
    if (err instanceof MissingPaymentIntentError) {
      return res.status(409).json({ error: err.message });
    }
    return next(err); // 500 via your error-handling middleware
  }
});
```

★ Insight ─────────────────────────────────────
Notice `Idempotency-Key` is a **required header**, not an optional field with a server-generated fallback. A server-generated key defeats the whole point — the client needs to hold the *same* key across its own retries (e.g. after a network timeout) for the dedup to work. Making it required is what turns "please remember to send an idempotency key" into "the request 400s until you do."
─────────────────────────────────────────────────

This covers the handler, schema additions, and migration end-to-end. One spot worth your judgment call rather than mine: the `RefundReason → Stripe reason` collapsing in `toStripeRefundReason` (three of five reasons map to `requested_by_customer`) — if your ops/finance team wants Stripe-side reporting to distinguish `order_cancelled` from `other`, that mapping is the one place to revisit.