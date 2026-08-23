Assumptions: Express, Zod, Prisma, and Stripe are installed; orders represent successfully paid Stripe Payment Intents. The required `Idempotency-Key` header prevents duplicate refunds.

```prisma
// prisma/schema.prisma

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

enum RefundReason {
  REQUESTED_BY_CUSTOMER
  DUPLICATE
  FRAUDULENT
}

enum RefundStatus {
  PENDING
  SUCCEEDED
  FAILED
}

model Order {
  id                    String   @id @default(uuid()) @db.Uuid
  tenantId              String   @db.Uuid
  totalCents            Int
  currency              String   @db.VarChar(3)
  stripePaymentIntentId String   @unique
  refunds               Refund[]

  @@unique([id, tenantId])
  @@index([tenantId])
}

model Refund {
  id                String       @id @default(uuid()) @db.Uuid
  orderId           String       @db.Uuid
  tenantId          String       @db.Uuid
  requestedByUserId String       @db.Uuid
  amountCents       Int
  reason            RefundReason
  status            RefundStatus @default(PENDING)
  idempotencyKey    String
  stripeRefundId    String?      @unique
  createdAt         DateTime     @default(now())
  updatedAt         DateTime     @updatedAt

  order Order @relation(fields: [orderId, tenantId], references: [id, tenantId], onDelete: Restrict)

  @@unique([orderId, idempotencyKey])
  @@index([tenantId, orderId])
}
```

```sql
-- prisma/migrations/20260822000000_add_refunds/migration.sql

CREATE TYPE "RefundReason" AS ENUM (
  'REQUESTED_BY_CUSTOMER',
  'DUPLICATE',
  'FRAUDULENT'
);

CREATE TYPE "RefundStatus" AS ENUM (
  'PENDING',
  'SUCCEEDED',
  'FAILED'
);

ALTER TABLE "Order"
  ADD COLUMN "stripePaymentIntentId" TEXT NOT NULL;

ALTER TABLE "Order"
  ADD CONSTRAINT "Order_id_tenantId_key" UNIQUE ("id", "tenantId");

CREATE TABLE "Refund" (
  "id" UUID NOT NULL DEFAULT gen_random_uuid(),
  "orderId" UUID NOT NULL,
  "tenantId" UUID NOT NULL,
  "requestedByUserId" UUID NOT NULL,
  "amountCents" INTEGER NOT NULL,
  "reason" "RefundReason" NOT NULL,
  "status" "RefundStatus" NOT NULL DEFAULT 'PENDING',
  "idempotencyKey" TEXT NOT NULL,
  "stripeRefundId" TEXT,
  "createdAt" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

  CONSTRAINT "Refund_pkey" PRIMARY KEY ("id"),
  CONSTRAINT "Refund_amountCents_positive" CHECK ("amountCents" > 0),
  CONSTRAINT "Refund_stripeRefundId_key" UNIQUE ("stripeRefundId"),
  CONSTRAINT "Refund_orderId_idempotencyKey_key" UNIQUE ("orderId", "idempotencyKey"),
  CONSTRAINT "Refund_orderId_tenantId_fkey"
    FOREIGN KEY ("orderId", "tenantId")
    REFERENCES "Order" ("id", "tenantId")
    ON UPDATE CASCADE
    ON DELETE RESTRICT
);

CREATE INDEX "Order_tenantId_idx" ON "Order" ("tenantId");
CREATE INDEX "Refund_tenantId_orderId_idx" ON "Refund" ("tenantId", "orderId");

-- Defense in depth: every application transaction must set app.tenant_id locally.
ALTER TABLE "Order" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "Order" FORCE ROW LEVEL SECURITY;
ALTER TABLE "Refund" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "Refund" FORCE ROW LEVEL SECURITY;

CREATE POLICY "Order_tenant_isolation" ON "Order"
  USING ("tenantId" = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK ("tenantId" = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

CREATE POLICY "Refund_tenant_isolation" ON "Refund"
  USING ("tenantId" = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK ("tenantId" = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
```

```ts
// src/http/refunds.ts

import type { Request, Response } from "express";
import Stripe from "stripe";
import { z } from "zod";
import {
  Prisma,
  PrismaClient,
  RefundReason,
  RefundStatus,
  type Refund,
} from "@prisma/client";

const prisma = new PrismaClient();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, {
  apiVersion: "2025-06-30.basil",
});

type SessionRequest = Request & {
  session?: {
    userId: string;
    tenantId: string;
  };
};

const sessionSchema = z.object({
  userId: z.string().uuid(),
  tenantId: z.string().uuid(),
});

const refundReasonSchema = z.enum([
  "requested_by_customer",
  "duplicate",
  "fraudulent",
]);

const refundRequestSchema = z.object({
  orderId: z.string().uuid(),
  amountCents: z.number().int().positive().max(100_000_000),
  reason: refundReasonSchema,
});

const idempotencyKeySchema = z.string().trim().min(1).max(255);

const prismaReason: Record<
  z.infer<typeof refundReasonSchema>,
  RefundReason
> = {
  requested_by_customer: RefundReason.REQUESTED_BY_CUSTOMER,
  duplicate: RefundReason.DUPLICATE,
  fraudulent: RefundReason.FRAUDULENT,
};

const apiReason: Record<RefundReason, z.infer<typeof refundReasonSchema>> = {
  REQUESTED_BY_CUSTOMER: "requested_by_customer",
  DUPLICATE: "duplicate",
  FRAUDULENT: "fraudulent",
};

function toResponse(refund: Refund) {
  return {
    id: refund.id,
    orderId: refund.orderId,
    amountCents: refund.amountCents,
    reason: apiReason[refund.reason],
    status: refund.status.toLowerCase(),
    stripeRefundId: refund.stripeRefundId,
    createdAt: refund.createdAt.toISOString(),
  };
}

function stripeStatusToDatabaseStatus(status: Stripe.Refund.Status): RefundStatus {
  switch (status) {
    case "pending":
      return RefundStatus.PENDING;
    case "succeeded":
      return RefundStatus.SUCCEEDED;
    case "failed":
    case "canceled":
      return RefundStatus.FAILED;
    default: {
      const exhaustive: never = status;
      throw new Error(`Unhandled Stripe refund status: ${exhaustive}`);
    }
  }
}

export async function createRefund(
  req: SessionRequest,
  res: Response,
): Promise<void> {
  const session = sessionSchema.safeParse(req.session);
  if (!session.success) {
    res.status(401).json({ error: "Authentication is required." });
    return;
  }

  const body = refundRequestSchema.safeParse(req.body);
  if (!body.success) {
    res.status(400).json({
      error: "Invalid refund request.",
      details: body.error.flatten(),
    });
    return;
  }

  const header = req.header("Idempotency-Key");
  const idempotencyKey = idempotencyKeySchema.safeParse(header);
  if (!idempotencyKey.success) {
    res.status(400).json({
      error: "A non-empty Idempotency-Key header of at most 255 characters is required.",
    });
    return;
  }

  const input = body.data;
  const actor = session.data;

  let reservedRefund: Refund;
  let paymentIntentId: string;
  let expectedCurrency: string;

  try {
    ({ reservedRefund, paymentIntentId, expectedCurrency } =
      await prisma.$transaction(
        async (tx) => {
          // Required for the RLS policies, scoped to this transaction only.
          await tx.$executeRaw`
            SELECT set_config('app.tenant_id', ${actor.tenantId}, true)
          `;

          // Serializes refund reservations for this order.
          const orders = await tx.$queryRaw<
            Array<{
              id: string;
              totalCents: number;
              currency: string;
              stripePaymentIntentId: string;
            }>
          >`
            SELECT "id", "totalCents", "currency", "stripePaymentIntentId"
            FROM "Order"
            WHERE "id" = ${input.orderId}
              AND "tenantId" = ${actor.tenantId}
            FOR UPDATE
          `;

          const order = orders[0];
          if (!order) {
            throw new HttpError(404, "Order not found.");
          }

          const existing = await tx.refund.findFirst({
            where: {
              orderId: input.orderId,
              tenantId: actor.tenantId,
              idempotencyKey: idempotencyKey.data,
            },
          });

          if (existing) {
            if (
              existing.amountCents !== input.amountCents ||
              existing.reason !== prismaReason[input.reason]
            ) {
              throw new HttpError(
                409,
                "Idempotency-Key was already used with a different refund request.",
              );
            }

            return {
              reservedRefund: existing,
              paymentIntentId: order.stripePaymentIntentId,
              expectedCurrency: order.currency,
            };
          }

          const reserved = await tx.refund.aggregate({
            _sum: { amountCents: true },
            where: {
              orderId: input.orderId,
              tenantId: actor.tenantId,
              status: {
                in: [RefundStatus.PENDING, RefundStatus.SUCCEEDED],
              },
            },
          });

          const alreadyReservedCents = reserved._sum.amountCents ?? 0;
          if (alreadyReservedCents + input.amountCents > order.totalCents) {
            throw new HttpError(
              422,
              "Refund amount exceeds the remaining refundable order balance.",
            );
          }

          const created = await tx.refund.create({
            data: {
              orderId: input.orderId,
              tenantId: actor.tenantId,
              requestedByUserId: actor.userId,
              amountCents: input.amountCents,
              reason: prismaReason[input.reason],
              idempotencyKey: idempotencyKey.data,
            },
          });

          return {
            reservedRefund: created,
            paymentIntentId: order.stripePaymentIntentId,
            expectedCurrency: order.currency,
          };
        },
        { isolationLevel: Prisma.TransactionIsolationLevel.Serializable },
      ));
  } catch (error) {
    return sendError(res, error);
  }

  if (reservedRefund.status === RefundStatus.SUCCEEDED) {
    res.status(200).json({ refund: toResponse(reservedRefund) });
    return;
  }

  try {
    const stripeRefund = await stripe.refunds.create(
      {
        payment_intent: paymentIntentId,
        amount: reservedRefund.amountCents,
        reason: input.reason,
        metadata: {
          orderId: reservedRefund.orderId,
          tenantId: actor.tenantId,
          localRefundId: reservedRefund.id,
          requestedByUserId: actor.userId,
        },
      },
      { idempotencyKey: reservedRefund.idempotencyKey },
    );

    if (
      stripeRefund.amount !== reservedRefund.amountCents ||
      stripeRefund.currency.toUpperCase() !== expectedCurrency.toUpperCase()
    ) {
      throw new Error(
        `Stripe refund ${stripeRefund.id} did not match the reserved amount or currency.`,
      );
    }

    const saved = await prisma.$transaction(async (tx) => {
      await tx.$executeRaw`
        SELECT set_config('app.tenant_id', ${actor.tenantId}, true)
      `;

      return tx.refund.update({
        where: { id: reservedRefund.id },
        data: {
          stripeRefundId: stripeRefund.id,
          status: stripeStatusToDatabaseStatus(stripeRefund.status),
        },
      });
    });

    res.status(201).json({ refund: toResponse(saved) });
  } catch (error) {
    // Keep the reservation PENDING. A retry with the same idempotency key is safe:
    // Stripe will return the original refund rather than create a second one.
    return sendError(
      res,
      new HttpError(
        502,
        "Refund outcome is pending confirmation. Retry using the same Idempotency-Key.",
        error,
      ),
    );
  }
}

class HttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly cause?: unknown,
  ) {
    super(message);
  }
}

function sendError(res: Response, error: unknown): void {
  if (error instanceof HttpError) {
    res.status(error.status).json({ error: error.message });
    return;
  }

  if (error instanceof Prisma.PrismaClientKnownRequestError) {
    res.status(409).json({ error: "Refund request conflicts with existing data." });
    return;
  }

  res.status(500).json({ error: "Unable to process refund." });
}
```

This makes cross-tenant refunding impossible at both query and database-policy layers, reserves refund value under an order lock to prevent over-refunds, and requires a Stripe/database idempotency key so retries do not create duplicate refunds.