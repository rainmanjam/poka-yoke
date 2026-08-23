I'll write this directly with the mistake-proofing baked in: tenant-scoped order lookup, an over-refund guard enforced both in a locked transaction and as a DB constraint, and a Stripe idempotency key tied to the Refund row so retries can't double-refund.

**Assumptions:** Express-style handler; `Order` gets a `stripePaymentIntentId` column (Stripe needs something to refund against); `Refund` gains `tenantId`, `status`, `stripeRefundId`, `requestedByUserId`. Refund is persisted as `pending` *before* the Stripe call, then marked `succeeded`/`failed`.

### `prisma/schema.prisma` (additions)

```prisma
enum RefundStatus {
  pending
  succeeded
  failed
}

model Order {
  id                    String   @id @default(uuid())
  tenantId              String
  totalCents            Int
  currency              String
  stripePaymentIntentId String?  // NEW: what Stripe refunds against
  refunds               Refund[]

  @@index([tenantId])
}

model Refund {
  id                String       @id @default(uuid())
  orderId           String
  tenantId          String       // NEW: denormalised so every refund query can be tenant-scoped
  amountCents       Int
  reason            String
  status            RefundStatus @default(pending) // NEW
  stripeRefundId    String?      @unique            // NEW: one Stripe refund per row, never two
  requestedByUserId String                          // NEW: audit trail
  createdAt         DateTime     @default(now())
  order             Order        @relation(fields: [orderId], references: [id])

  @@index([orderId])
  @@index([tenantId, createdAt])
}
```

### `prisma/migrations/20260822000000_refund_endpoint/migration.sql`

```sql
CREATE TYPE "RefundStatus" AS ENUM ('pending', 'succeeded', 'failed');

ALTER TABLE "Order" ADD COLUMN "stripePaymentIntentId" TEXT;
CREATE INDEX "Order_tenantId_idx" ON "Order"("tenantId");

-- Backfill tenantId from the parent order, then make it NOT NULL.
ALTER TABLE "Refund" ADD COLUMN "tenantId" TEXT;
UPDATE "Refund" r SET "tenantId" = o."tenantId" FROM "Order" o WHERE o.id = r."orderId";
ALTER TABLE "Refund" ALTER COLUMN "tenantId" SET NOT NULL;

ALTER TABLE "Refund"
  ADD COLUMN "status" "RefundStatus" NOT NULL DEFAULT 'succeeded', -- existing rows already happened
  ADD COLUMN "stripeRefundId" TEXT,
  ADD COLUMN "requestedByUserId" TEXT NOT NULL DEFAULT 'system';
ALTER TABLE "Refund" ALTER COLUMN "status" SET DEFAULT 'pending';
ALTER TABLE "Refund" ALTER COLUMN "requestedByUserId" DROP DEFAULT;

CREATE UNIQUE INDEX "Refund_stripeRefundId_key" ON "Refund"("stripeRefundId");
CREATE INDEX "Refund_orderId_idx" ON "Refund"("orderId");
CREATE INDEX "Refund_tenantId_createdAt_idx" ON "Refund"("tenantId", "createdAt");

-- Devices: the DB refuses what the handler should never send.
ALTER TABLE "Refund" ADD CONSTRAINT "Refund_amount_positive" CHECK ("amountCents" > 0);
ALTER TABLE "Refund" ADD CONSTRAINT "Refund_tenant_matches_order"
  FOREIGN KEY ("orderId", "tenantId") REFERENCES "Order"("id", "tenantId");
-- The composite FK above needs a matching unique on Order:
ALTER TABLE "Order" ADD CONSTRAINT "Order_id_tenantId_key" UNIQUE ("id", "tenantId");
```

### `src/refunds/handler.ts`

```ts
import { Prisma, PrismaClient, RefundStatus } from "@prisma/client";
import Stripe from "stripe";
import { z } from "zod";
import type { Request, Response } from "express";

const prisma = new PrismaClient();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, { apiVersion: "2025-02-24.acacia" });

const RefundBody = z.object({
  orderId: z.string().uuid(),
  amountCents: z.number().int().positive(),
  reason: z.string().trim().min(1).max(500),
});

interface Session { userId: string; tenantId: string }
type AuthedRequest = Request & { session: Session };

class RefundError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function postRefund(req: AuthedRequest, res: Response) {
  const parsed = RefundBody.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: parsed.error.flatten() });
  const { orderId, amountCents, reason } = parsed.data;
  const { userId, tenantId } = req.session;

  try {
    // 1. Reserve the refund inside a transaction that locks the order row, so two
    //    concurrent requests cannot both pass the remaining-balance check.
    const pending = await prisma.$transaction(async (tx) => {
      const [order] = await tx.$queryRaw<
        { id: string; totalCents: number; stripePaymentIntentId: string | null }[]
      >(Prisma.sql`
        SELECT id, "totalCents", "stripePaymentIntentId" FROM "Order"
        WHERE id = ${orderId} AND "tenantId" = ${tenantId}
        FOR UPDATE
      `);
      // Tenant-scoped lookup: a foreign order is indistinguishable from a missing one.
      if (!order) throw new RefundError(404, "Order not found");
      if (!order.stripePaymentIntentId) throw new RefundError(409, "Order has no captured payment");

      const { _sum } = await tx.refund.aggregate({
        where: { orderId, tenantId, status: { in: [RefundStatus.pending, RefundStatus.succeeded] } },
        _sum: { amountCents: true },
      });
      const remaining = order.totalCents - (_sum.amountCents ?? 0);
      if (amountCents > remaining) {
        throw new RefundError(422, `Refund exceeds refundable balance (${remaining} cents remaining)`);
      }

      const row = await tx.refund.create({
        data: { orderId, tenantId, amountCents, reason, requestedByUserId: userId, status: RefundStatus.pending },
      });
      return { row, paymentIntentId: order.stripePaymentIntentId };
    }, { isolationLevel: Prisma.TransactionIsolationLevel.ReadCommitted });

    // 2. Call Stripe. The idempotency key is our row id, so a retry after a
    //    timeout returns the same Stripe refund instead of issuing a second one.
    let stripeRefund: Stripe.Refund;
    try {
      stripeRefund = await stripe.refunds.create(
        {
          payment_intent: pending.paymentIntentId,
          amount: amountCents,
          reason: "requested_by_customer",
          metadata: { refundId: pending.row.id, orderId, tenantId, reason },
        },
        { idempotencyKey: `refund:${pending.row.id}` },
      );
    } catch (err) {
      // Mark failed so the reserved amount is released; the row stays as audit evidence.
      await prisma.refund.update({ where: { id: pending.row.id }, data: { status: RefundStatus.failed } });
      const msg = err instanceof Stripe.errors.StripeError ? err.message : "Stripe refund failed";
      throw new RefundError(502, msg);
    }

    // 3. Persist the outcome.
    const refund = await prisma.refund.update({
      where: { id: pending.row.id },
      data: {
        stripeRefundId: stripeRefund.id,
        status: stripeRefund.status === "failed" ? RefundStatus.failed : RefundStatus.succeeded,
      },
    });
    return res.status(201).json(refund);
  } catch (err) {
    if (err instanceof RefundError) return res.status(err.status).json({ error: err.message });
    throw err; // let the app-level error handler log 500s
  }
}
```

`★ Insight ─────────────────────────────────────`
- **Pending-before-call**: writing the Refund row *before* calling Stripe is what makes the idempotency key possible — the key has to exist before the network call it protects. A crash between steps 2 and 3 leaves a `pending` row with no `stripeRefundId`; a reconciliation job can query Stripe by `metadata.refundId` to repair it, rather than guessing.
- **`FOR UPDATE` + `CHECK` + composite FK**: the balance check lives in the transaction, but the positive-amount and tenant-matches-order rules are also in Postgres, so a future handler that forgets them gets rejected rather than silently writing bad data.
- **404 for foreign tenants**: returning 403 would confirm the order exists elsewhere — an enumeration oracle.
`─────────────────────────────────────────────────`

**Recap:** Delivered the schema additions, migration, and handler for `POST /refunds`. Devices included: tenant-scoped locked order read, cumulative over-refund guard, DB-level `CHECK`/composite-FK constraints, Stripe idempotency keyed on the Refund row, and a `pending → succeeded | failed` status so partial failures are visible instead of lost. Not included: a reconciliation job for rows stuck in `pending`, and tests — both worth adding next.