I'll write this inline as requested, designing the endpoint so the money-class mistakes (cross-tenant refund, over-refund, double-refund on retry, Stripe-succeeded-but-DB-failed) are structurally prevented rather than left to discipline.

★ Insight ─────────────────────────────────────
- **Persist before calling Stripe, not after.** If you call Stripe first and the DB write fails, money has left and nothing records it. Creating a `pending` row first and using its ID as the Stripe idempotency key means a retry of the same row converges on the same Stripe refund.
- **Over-refund must be enforced where the race lives.** Two concurrent requests each see "$50 remaining" and both refund $50. A `SELECT ... FOR UPDATE` on the order inside the transaction serializes them; a DB `CHECK (amountCents > 0)` backstops the app.
- **`Order` has no `stripePaymentIntentId` in the given schema** — a refund can't be issued without it, so I'm adding it as an assumption.
─────────────────────────────────────────────────

## Prisma schema additions

```prisma
// prisma/schema.prisma

enum RefundStatus {
  pending
  succeeded
  failed
}

model Order {
  id                    String   @id @default(cuid())
  tenantId              String
  totalCents            Int
  currency              String
  stripePaymentIntentId String?  // ADDED: required to refund via Stripe
  refunds               Refund[]

  @@index([tenantId])
}

model Refund {
  id                String       @id @default(cuid())
  orderId           String
  order             Order        @relation(fields: [orderId], references: [id])
  tenantId          String                              // ADDED: denormalised so every query can scope on it
  amountCents       Int
  currency          String                              // ADDED: snapshot; never re-derive money from the parent
  reason            String
  status            RefundStatus @default(pending)      // ADDED
  stripeRefundId    String?      @unique                // ADDED: unique = a Stripe refund can be recorded once
  failureMessage    String?                             // ADDED
  requestedByUserId String                              // ADDED: audit trail
  idempotencyKey    String?                             // ADDED: client-supplied key, unique per tenant
  createdAt         DateTime     @default(now())
  updatedAt         DateTime     @updatedAt

  @@unique([tenantId, idempotencyKey])
  @@index([orderId])
  @@index([tenantId, orderId])
}
```

## Migration

```sql
-- prisma/migrations/20260822000000_refund_endpoint/migration.sql

CREATE TYPE "RefundStatus" AS ENUM ('pending', 'succeeded', 'failed');

ALTER TABLE "Order" ADD COLUMN "stripePaymentIntentId" TEXT;

ALTER TABLE "Refund"
  ADD COLUMN "tenantId"          TEXT,
  ADD COLUMN "currency"          TEXT,
  ADD COLUMN "status"            "RefundStatus" NOT NULL DEFAULT 'pending',
  ADD COLUMN "stripeRefundId"    TEXT,
  ADD COLUMN "failureMessage"    TEXT,
  ADD COLUMN "requestedByUserId" TEXT,
  ADD COLUMN "idempotencyKey"    TEXT,
  ADD COLUMN "updatedAt"         TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- Backfill existing rows from their parent order so NOT NULL can be enforced.
UPDATE "Refund" r
SET "tenantId" = o."tenantId",
    "currency" = o."currency",
    "status"   = 'succeeded',
    "requestedByUserId" = 'backfill'
FROM "Order" o
WHERE r."orderId" = o."id";

ALTER TABLE "Refund"
  ALTER COLUMN "tenantId"          SET NOT NULL,
  ALTER COLUMN "currency"          SET NOT NULL,
  ALTER COLUMN "requestedByUserId" SET NOT NULL;

-- Devices: the database refuses what the app must never write.
ALTER TABLE "Refund" ADD CONSTRAINT "Refund_amountCents_positive" CHECK ("amountCents" > 0);
ALTER TABLE "Refund" ADD CONSTRAINT "Refund_orderId_fkey"
  FOREIGN KEY ("orderId") REFERENCES "Order"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE UNIQUE INDEX "Refund_stripeRefundId_key" ON "Refund"("stripeRefundId");
CREATE UNIQUE INDEX "Refund_tenantId_idempotencyKey_key" ON "Refund"("tenantId", "idempotencyKey");
CREATE INDEX "Refund_orderId_idx" ON "Refund"("orderId");
CREATE INDEX "Refund_tenantId_orderId_idx" ON "Refund"("tenantId", "orderId");
CREATE INDEX "Order_tenantId_idx" ON "Order"("tenantId");

-- Cross-tenant integrity: a refund's tenant must equal its order's tenant.
CREATE OR REPLACE FUNCTION refund_tenant_matches_order() RETURNS trigger AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM "Order" WHERE "id" = NEW."orderId" AND "tenantId" = NEW."tenantId") THEN
    RAISE EXCEPTION 'Refund.tenantId % does not match Order %', NEW."tenantId", NEW."orderId";
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER "Refund_tenant_check"
  BEFORE INSERT OR UPDATE OF "orderId", "tenantId" ON "Refund"
  FOR EACH ROW EXECUTE FUNCTION refund_tenant_matches_order();
```

## Handler

```ts
// src/refunds/refund.handler.ts
import { Request, Response, NextFunction, Router } from "express";
import { Prisma, PrismaClient, RefundStatus } from "@prisma/client";
import Stripe from "stripe";
import { z } from "zod";

const prisma = new PrismaClient();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, { apiVersion: "2025-07-30.basil" });

// ---- Session contract (assumed provided by existing auth middleware) ----
interface Session { userId: string; tenantId: string }
type AuthedRequest = Request & { session: Session };

// ---- Input: parse, don't validate ----
const RefundRequest = z.object({
  orderId: z.string().min(1),
  amountCents: z.number().int().positive(),           // zero/negative/fractional cents cannot enter
  reason: z.enum(["duplicate", "fraudulent", "requested_by_customer"]), // Stripe's vocabulary
});
type RefundRequest = z.infer<typeof RefundRequest>;

class RefundError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

// ---- Step 1: reserve the refund inside a transaction (no network calls here) ----
async function reserveRefund(session: Session, input: RefundRequest, idempotencyKey: string | undefined) {
  return prisma.$transaction(async (tx) => {
    // Idempotent replay: same tenant + key returns the existing row, whatever state it's in.
    if (idempotencyKey) {
      const existing = await tx.refund.findUnique({
        where: { tenantId_idempotencyKey: { tenantId: session.tenantId, idempotencyKey } },
      });
      if (existing) return { refund: existing, replay: true as const, paymentIntentId: null };
    }

    // Lock the order row so concurrent refunds serialize on the remaining-balance check.
    // Tenant scoping is in the WHERE: another tenant's orderId is simply "not found", never 403.
    const [order] = await tx.$queryRaw<
      { id: string; totalCents: number; currency: string; stripePaymentIntentId: string | null }[]
    >(Prisma.sql`
      SELECT "id", "totalCents", "currency", "stripePaymentIntentId"
      FROM "Order"
      WHERE "id" = ${input.orderId} AND "tenantId" = ${session.tenantId}
      FOR UPDATE
    `);
    if (!order) throw new RefundError(404, "Order not found");
    if (!order.stripePaymentIntentId) throw new RefundError(409, "Order has no captured payment to refund");

    // Count pending as committed: a pending refund may still succeed at Stripe.
    const agg = await tx.refund.aggregate({
      where: { orderId: order.id, status: { in: [RefundStatus.pending, RefundStatus.succeeded] } },
      _sum: { amountCents: true },
    });
    const alreadyRefunded = agg._sum.amountCents ?? 0;
    const remaining = order.totalCents - alreadyRefunded;
    if (input.amountCents > remaining) {
      throw new RefundError(422, `Refund exceeds refundable balance (${remaining} ${order.currency})`);
    }

    const refund = await tx.refund.create({
      data: {
        orderId: order.id,
        tenantId: session.tenantId,
        amountCents: input.amountCents,
        currency: order.currency,
        reason: input.reason,
        status: RefundStatus.pending,
        requestedByUserId: session.userId,
        idempotencyKey: idempotencyKey ?? null,
      },
    });
    return { refund, replay: false as const, paymentIntentId: order.stripePaymentIntentId };
  }, { isolationLevel: Prisma.TransactionIsolationLevel.ReadCommitted });
}

// ---- Step 2: execute at Stripe, keyed by OUR row id so retries converge ----
async function executeAtStripe(refundId: string, paymentIntentId: string, amountCents: number, reason: RefundRequest["reason"]) {
  try {
    const stripeRefund = await stripe.refunds.create(
      { payment_intent: paymentIntentId, amount: amountCents, reason, metadata: { refundId } },
      { idempotencyKey: `refund:${refundId}` },
    );
    return prisma.refund.update({
      where: { id: refundId },
      data: {
        stripeRefundId: stripeRefund.id,
        status: stripeRefund.status === "failed" ? RefundStatus.failed : RefundStatus.succeeded,
        failureMessage: stripeRefund.failure_reason ?? null,
      },
    });
  } catch (err) {
    // Stripe rejected (or network died before a response). Record it — a pending row that
    // nobody reconciles is a silent failure. Network ambiguity is resolved by the reconciler
    // (see note below), not by guessing here.
    const message = err instanceof Stripe.errors.StripeError ? err.message : "Stripe call failed";
    const isDefinitiveRejection = err instanceof Stripe.errors.StripeInvalidRequestError
      || err instanceof Stripe.errors.StripeCardError;
    if (isDefinitiveRejection) {
      await prisma.refund.update({ where: { id: refundId }, data: { status: RefundStatus.failed, failureMessage: message } });
      throw new RefundError(402, message);
    }
    throw new RefundError(502, "Refund is pending; Stripe did not confirm. Retry with the same Idempotency-Key.");
  }
}

export async function createRefund(req: AuthedRequest, res: Response, next: NextFunction) {
  try {
    const input = RefundRequest.parse(req.body);
    const idempotencyKey = req.header("Idempotency-Key") || undefined;

    const reserved = await reserveRefund(req.session, input, idempotencyKey);

    if (reserved.replay) {
      // Already succeeded/failed → return as-is. Still pending → finish the Stripe leg (same key → same refund).
      if (reserved.refund.status !== RefundStatus.pending) return res.status(200).json(toDto(reserved.refund));
      const order = await prisma.order.findFirstOrThrow({ where: { id: reserved.refund.orderId, tenantId: req.session.tenantId } });
      const done = await executeAtStripe(reserved.refund.id, order.stripePaymentIntentId!, reserved.refund.amountCents, input.reason);
      return res.status(200).json(toDto(done));
    }

    const done = await executeAtStripe(reserved.refund.id, reserved.paymentIntentId!, input.amountCents, input.reason);
    return res.status(201).json(toDto(done));
  } catch (err) {
    if (err instanceof z.ZodError) return res.status(400).json({ error: err.flatten() });
    if (err instanceof RefundError) return res.status(err.status).json({ error: err.message });
    return next(err);
  }
}

// Explicit DTO: internal columns (requestedByUserId, idempotencyKey) never leak by accident.
function toDto(r: { id: string; orderId: string; amountCents: number; currency: string; reason: string; status: RefundStatus; stripeRefundId: string | null; failureMessage: string | null; createdAt: Date }) {
  return {
    id: r.id, orderId: r.orderId, amountCents: r.amountCents, currency: r.currency,
    reason: r.reason, status: r.status, stripeRefundId: r.stripeRefundId,
    failureMessage: r.failureMessage, createdAt: r.createdAt.toISOString(),
  };
}

export const refundsRouter = Router().post("/refunds", requireSession, createRefund);

function requireSession(req: Request, res: Response, next: NextFunction) {
  const s = (req as Partial<AuthedRequest>).session;
  if (!s?.userId || !s?.tenantId) return res.status(401).json({ error: "Unauthenticated" });
  next();
}
```

## Assumptions and one thing left deliberately unsolved

- **Assumed:** Express, Zod, Stripe Node SDK ≥ 18, `Order.stripePaymentIntentId` populated at capture time, and `reason` restricted to Stripe's three values (a free-text reason would need a separate `note` column).
- **Not covered:** a `pending` row whose Stripe call timed out ambiguously. The handler records it and returns 502 with retry guidance, but you need a reconciler — a cron that lists `pending` refunds older than N minutes and queries Stripe by `metadata.refundId` (or a `refund.updated` webhook) — to settle them. Without it, pending rows permanently reduce the refundable balance. That's the one item here that still relies on someone remembering.