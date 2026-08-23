Assumption: Express authentication exposes `req.session`, and clients must send an `Idempotency-Key` header so retries cannot create duplicate Stripe refunds.

```prisma
// prisma/schema.prisma — relevant models

model Order {
  id                    String   @id
  tenantId              String
  totalCents            Int
  currency              String
  stripePaymentIntentId String?  @unique
  refunds               Refund[]

  // Enables a tenant-safe composite foreign key from Refund.
  @@unique([id, tenantId])
}

model Refund {
  id                String   @id @default(cuid())
  orderId           String
  tenantId          String
  amountCents       Int
  currency          String
  reason            String
  status            String   @default("legacy")
  stripeRefundId    String?  @unique
  idempotencyKey    String?  @unique
  requestedByUserId String?
  createdAt         DateTime @default(now())

  order Order @relation(
    fields:     [orderId, tenantId],
    references: [id, tenantId],
    onDelete:   Restrict
  )

  @@index([tenantId, createdAt])
  @@index([orderId, status])
}
```

```sql
-- prisma/migrations/20260822000000_add_stripe_refunds/migration.sql

ALTER TABLE "Order"
  ADD COLUMN "stripePaymentIntentId" TEXT;

CREATE UNIQUE INDEX "Order_stripePaymentIntentId_key"
  ON "Order"("stripePaymentIntentId");

ALTER TABLE "Order"
  ADD CONSTRAINT "Order_id_tenantId_key" UNIQUE ("id", "tenantId");

ALTER TABLE "Refund"
  ADD COLUMN "tenantId" TEXT,
  ADD COLUMN "currency" TEXT,
  ADD COLUMN "status" TEXT NOT NULL DEFAULT 'legacy',
  ADD COLUMN "stripeRefundId" TEXT,
  ADD COLUMN "idempotencyKey" TEXT,
  ADD COLUMN "requestedByUserId" TEXT;

-- Backfill required tenant/currency values from each refund's order.
-- This deliberately fails later if historical refunds have no valid order.
UPDATE "Refund" AS r
SET
  "tenantId" = o."tenantId",
  "currency" = o."currency"
FROM "Order" AS o
WHERE r."orderId" = o."id";

ALTER TABLE "Refund"
  ALTER COLUMN "tenantId" SET NOT NULL,
  ALTER COLUMN "currency" SET NOT NULL;

CREATE UNIQUE INDEX "Refund_stripeRefundId_key"
  ON "Refund"("stripeRefundId");

CREATE UNIQUE INDEX "Refund_idempotencyKey_key"
  ON "Refund"("idempotencyKey");

CREATE INDEX "Refund_tenantId_createdAt_idx"
  ON "Refund"("tenantId", "createdAt");

CREATE INDEX "Refund_orderId_status_idx"
  ON "Refund"("orderId", "status");

ALTER TABLE "Refund"
  ADD CONSTRAINT "Refund_orderId_tenantId_fkey"
  FOREIGN KEY ("orderId", "tenantId")
  REFERENCES "Order"("id", "tenantId")
  ON DELETE RESTRICT
  ON UPDATE CASCADE;
```

```ts
// src/routes/refunds.ts
import { createHash } from "node:crypto";
import type { Request, Response, NextFunction } from "express";
import Stripe from "stripe";
import { PrismaClient, Prisma } from "@prisma/client";

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

type RefundBody = {
  orderId: unknown;
  amountCents: unknown;
  reason: unknown;
};

class HttpError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

function requireSession(req: AuthenticatedRequest) {
  if (!req.session?.userId || !req.session?.tenantId) {
    throw new HttpError(401, "Authentication is required.");
  }

  return req.session;
}

function parseBody(body: RefundBody) {
  const { orderId, amountCents, reason } = body;

  if (typeof orderId !== "string" || orderId.length === 0) {
    throw new HttpError(400, "orderId must be a non-empty string.");
  }

  if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
    throw new HttpError(400, "amountCents must be a positive integer.");
  }

  if (
    typeof reason !== "string" ||
    reason.trim().length === 0 ||
    reason.length > 500
  ) {
    throw new HttpError(400, "reason must be between 1 and 500 characters.");
  }

  return { orderId, amountCents, reason: reason.trim() };
}

function requestIdempotencyKey(
  req: AuthenticatedRequest,
  tenantId: string,
): string {
  const suppliedKey = req.header("Idempotency-Key");

  if (!suppliedKey || suppliedKey.length > 200) {
    throw new HttpError(
      400,
      "A valid Idempotency-Key header of at most 200 characters is required.",
    );
  }

  // Hashing scopes the client key to its tenant and keeps the Stripe key short.
  return createHash("sha256")
    .update(`${tenantId}:${suppliedKey}`)
    .digest("hex");
}

function assertSameRefundRequest(
  refund: {
    orderId: string;
    amountCents: number;
    reason: string;
  },
  input: { orderId: string; amountCents: number; reason: string },
) {
  if (
    refund.orderId !== input.orderId ||
    refund.amountCents !== input.amountCents ||
    refund.reason !== input.reason
  ) {
    throw new HttpError(
      409,
      "This Idempotency-Key was already used for a different refund request.",
    );
  }
}

export async function createRefund(
  req: AuthenticatedRequest,
  res: Response,
  next: NextFunction,
) {
  try {
    const { userId, tenantId } = requireSession(req);
    const input = parseBody(req.body as RefundBody);
    const idempotencyKey = requestIdempotencyKey(req, tenantId);

    let refund = await prisma.refund.findUnique({
      where: { idempotencyKey },
    });

    if (refund) {
      assertSameRefundRequest(refund, input);

      // A completed Stripe refund is safe to return immediately.
      if (refund.stripeRefundId) {
        return res.status(200).json({ refund });
      }
    }

    const order = await prisma.order.findFirst({
      where: {
        id: input.orderId,
        tenantId,
      },
      select: {
        id: true,
        totalCents: true,
        currency: true,
        stripePaymentIntentId: true,
      },
    });

    if (!order) {
      throw new HttpError(404, "Order not found.");
    }

    if (!order.stripePaymentIntentId) {
      throw new HttpError(
        409,
        "This order has no Stripe PaymentIntent and cannot be refunded.",
      );
    }

    if (!refund) {
      const priorRefunds = await prisma.refund.aggregate({
        where: {
          orderId: order.id,
          status: { notIn: ["failed", "canceled"] },
        },
        _sum: { amountCents: true },
      });

      const refundedCents = priorRefunds._sum.amountCents ?? 0;

      if (refundedCents + input.amountCents > order.totalCents) {
        throw new HttpError(409, "Refund amount exceeds the remaining balance.");
      }

      try {
        refund = await prisma.refund.create({
          data: {
            orderId: order.id,
            tenantId,
            amountCents: input.amountCents,
            currency: order.currency,
            reason: input.reason,
            status: "pending",
            idempotencyKey,
            requestedByUserId: userId,
          },
        });
      } catch (error) {
        // A concurrent retry may have created the pending row first.
        if (!(error instanceof Prisma.PrismaClientKnownRequestError) ||
            error.code !== "P2002") {
          throw error;
        }

        refund = await prisma.refund.findUnique({
          where: { idempotencyKey },
        });

        if (!refund) throw error;
        assertSameRefundRequest(refund, input);

        if (refund.stripeRefundId) {
          return res.status(200).json({ refund });
        }
      }
    }

    const stripeRefund = await stripe.refunds.create(
      {
        payment_intent: order.stripePaymentIntentId,
        amount: input.amountCents,
        metadata: {
          orderId: order.id,
          tenantId,
          refundId: refund.id,
          reason: input.reason,
        },
      },
      {
        // Stripe returns the same refund if this request is retried after a timeout.
        idempotencyKey: `refund:${idempotencyKey}`,
      },
    );

    const persistedRefund = await prisma.refund.update({
      where: { id: refund.id },
      data: {
        stripeRefundId: stripeRefund.id,
        status: stripeRefund.status ?? "pending",
      },
    });

    return res.status(201).json({ refund: persistedRefund });
  } catch (error) {
    if (error instanceof Stripe.errors.StripeInvalidRequestError) {
      return res.status(409).json({ error: error.message });
    }

    if (error instanceof HttpError) {
      return res.status(error.status).json({ error: error.message });
    }

    return next(error);
  }
}
```

The handler scopes every order lookup to the authenticated tenant, records a pending row before contacting Stripe, and uses the same idempotency key for both local persistence and Stripe retries.