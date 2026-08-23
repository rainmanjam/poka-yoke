Assumption: each order stores its Stripe PaymentIntent ID. The endpoint prevents cross-tenant access and over-refunds, uses a Stripe idempotency key, and persists Stripe’s refund ID.

```prisma
// prisma/schema.prisma

model Order {
  id                    String   @id @default(uuid())
  tenantId              String
  totalCents            Int
  currency              String
  stripePaymentIntentId String   @unique
  refundedCents         Int      @default(0)

  refunds Refund[]

  @@index([tenantId])
}

model Refund {
  id             String   @id @default(uuid())
  orderId        String
  amountCents    Int
  reason         String?
  stripeRefundId String   @unique
  createdAt      DateTime @default(now())

  order Order @relation(fields: [orderId], references: [id], onDelete: Restrict)

  @@index([orderId])
}
```

```sql
-- prisma/migrations/20260822000000_add_stripe_refunds/migration.sql

ALTER TABLE "Order"
  ADD COLUMN "stripePaymentIntentId" TEXT,
  ADD COLUMN "refundedCents" INTEGER NOT NULL DEFAULT 0;

-- Backfill stripePaymentIntentId before making it NOT NULL in a follow-up
-- migration if existing orders already exist.

CREATE UNIQUE INDEX "Order_stripePaymentIntentId_key"
  ON "Order"("stripePaymentIntentId");

ALTER TABLE "Refund"
  ADD COLUMN "stripeRefundId" TEXT;

CREATE UNIQUE INDEX "Refund_stripeRefundId_key"
  ON "Refund"("stripeRefundId");

ALTER TABLE "Refund"
  ADD CONSTRAINT "Refund_orderId_fkey"
  FOREIGN KEY ("orderId") REFERENCES "Order"("id")
  ON DELETE RESTRICT ON UPDATE CASCADE;
```

```ts
// src/routes/refunds.ts

import { randomUUID } from "node:crypto";
import type { Request, Response } from "express";
import Stripe from "stripe";
import { Prisma, PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: "2025-07-30.basil",
});

type AuthenticatedRequest = Request & {
  session?: {
    userId: string;
    tenantId: string;
  };
};

const stripeReasons = new Set<Stripe.RefundCreateParams.Reason>([
  "duplicate",
  "fraudulent",
  "requested_by_customer",
]);

export async function createRefund(
  req: AuthenticatedRequest,
  res: Response,
): Promise<void> {
  const session = req.session;
  if (!session?.userId || !session.tenantId) {
    res.status(401).json({ error: "Authentication required" });
    return;
  }

  const { orderId, amountCents, reason } = req.body ?? {};

  if (typeof orderId !== "string" || orderId.length === 0) {
    res.status(400).json({ error: "orderId is required" });
    return;
  }

  if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
    res.status(400).json({ error: "amountCents must be a positive integer" });
    return;
  }

  if (reason !== undefined && !stripeReasons.has(reason)) {
    res.status(400).json({
      error: "reason must be duplicate, fraudulent, or requested_by_customer",
    });
    return;
  }

  const order = await prisma.order.findFirst({
    where: {
      id: orderId,
      tenantId: session.tenantId,
    },
    select: {
      id: true,
      totalCents: true,
      currency: true,
      refundedCents: true,
      stripePaymentIntentId: true,
    },
  });

  // Deliberately return 404 for both nonexistent and other-tenant orders.
  if (!order) {
    res.status(404).json({ error: "Order not found" });
    return;
  }

  if (!order.stripePaymentIntentId) {
    res.status(409).json({ error: "Order has no Stripe payment to refund" });
    return;
  }

  if (amountCents > order.totalCents - order.refundedCents) {
    res.status(409).json({ error: "Refund amount exceeds remaining balance" });
    return;
  }

  const idempotencyKey = `refund:${order.id}:${randomUUID()}`;

  let stripeRefund: Stripe.Refund;
  try {
    stripeRefund = await stripe.refunds.create(
      {
        payment_intent: order.stripePaymentIntentId,
        amount: amountCents,
        reason,
        metadata: {
          orderId: order.id,
          tenantId: session.tenantId,
          requestedByUserId: session.userId,
        },
      },
      { idempotencyKey },
    );
  } catch (error) {
    if (error instanceof Stripe.errors.StripeError) {
      res.status(error.statusCode ?? 502).json({
        error: "Stripe refund failed",
        code: error.code,
        message: error.message,
      });
      return;
    }
    throw error;
  }

  try {
    const refund = await prisma.$transaction(
      async (tx) => {
        // Conditional update is the concurrency guard: only one request may
        // reserve the remaining refundable balance.
        const updated = await tx.order.updateMany({
          where: {
            id: order.id,
            tenantId: session.tenantId,
            refundedCents: {
              lte: order.totalCents - amountCents,
            },
          },
          data: {
            refundedCents: {
              increment: amountCents,
            },
          },
        });

        if (updated.count !== 1) {
          throw new Error("REFUND_BALANCE_CHANGED");
        }

        return tx.refund.create({
          data: {
            orderId: order.id,
            amountCents,
            reason: reason ?? null,
            stripeRefundId: stripeRefund.id,
          },
        });
      },
      { isolationLevel: Prisma.TransactionIsolationLevel.Serializable },
    );

    res.status(201).json(refund);
  } catch (error) {
    // Stripe has already accepted this refund. Alert/reconcile this condition;
    // retrying with the same idempotency key retrieves the same Stripe refund.
    if (error instanceof Error && error.message === "REFUND_BALANCE_CHANGED") {
      res.status(409).json({
        error: "Refund was created in Stripe but could not be recorded because the balance changed",
        stripeRefundId: stripeRefund.id,
      });
      return;
    }

    throw error;
  }
}
```

```ts
// src/app.ts

import express from "express";
import { createRefund } from "./routes/refunds";

const app = express();
app.use(express.json());

// Mount after authentication middleware populates req.session.
app.post("/refunds", createRefund);

export default app;
```