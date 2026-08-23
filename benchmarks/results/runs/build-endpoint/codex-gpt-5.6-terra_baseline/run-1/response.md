Assumptions: IDs are `TEXT`/CUID-like; an order stores Stripe’s PaymentIntent ID after payment succeeds; `Idempotency-Key` is required to make retries safe.

```prisma
// prisma/schema.prisma

generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "postgresql"
  url      = env("DATABASE_URL")
}

enum RefundStatus {
  PENDING
  SUBMITTED
  FAILED
}

model Order {
  id                    String   @id @default(cuid())
  tenantId              String
  totalCents            Int
  currency              String   @db.VarChar(3)
  stripePaymentIntentId String?  @unique
  refunds               Refund[]

  @@index([tenantId])
}

model Refund {
  id             String       @id @default(cuid())
  orderId        String
  amountCents    Int
  reason         String       @db.VarChar(64)
  createdAt      DateTime     @default(now())
  idempotencyKey String       @unique @db.VarChar(255)
  stripeRefundId String?      @unique
  stripeStatus   String?      @db.VarChar(32)
  status         RefundStatus @default(PENDING)

  order Order @relation(fields: [orderId], references: [id], onDelete: Restrict)

  @@index([orderId, status])
}
```

```sql
-- prisma/migrations/20260822000000_add_stripe_refunds/migration.sql

CREATE TYPE "RefundStatus" AS ENUM ('PENDING', 'SUBMITTED', 'FAILED');

ALTER TABLE "Order"
  ADD COLUMN "stripePaymentIntentId" TEXT;

CREATE UNIQUE INDEX "Order_stripePaymentIntentId_key"
  ON "Order"("stripePaymentIntentId");

ALTER TABLE "Refund"
  ADD COLUMN "idempotencyKey" TEXT,
  ADD COLUMN "stripeRefundId" TEXT,
  ADD COLUMN "stripeStatus" VARCHAR(32),
  ADD COLUMN "status" "RefundStatus" NOT NULL DEFAULT 'SUBMITTED';

-- Existing rows cannot be safely replayed, but must receive unique keys.
UPDATE "Refund"
SET "idempotencyKey" = 'legacy:' || "id"::text
WHERE "idempotencyKey" IS NULL;

ALTER TABLE "Refund"
  ALTER COLUMN "idempotencyKey" SET NOT NULL;

CREATE UNIQUE INDEX "Refund_idempotencyKey_key"
  ON "Refund"("idempotencyKey");

CREATE UNIQUE INDEX "Refund_stripeRefundId_key"
  ON "Refund"("stripeRefundId");

CREATE INDEX "Refund_orderId_status_idx"
  ON "Refund"("orderId", "status");
```

```ts
// src/routes/refunds.ts

import { Prisma, PrismaClient, RefundStatus } from "@prisma/client";
import { NextFunction, Request, Response, Router } from "express";
import Stripe from "stripe";

type Session = {
  userId: string;
  tenantId: string;
};

type AuthenticatedRequest = Request & {
  session?: Session;
};

type RefundReason =
  | "duplicate"
  | "fraudulent"
  | "requested_by_customer";

type RefundInput = {
  orderId: string;
  amountCents: number;
  reason: RefundReason;
};

class HttpError extends Error {
  constructor(
    public readonly statusCode: number,
    message: string,
  ) {
    super(message);
  }
}

const ALLOWED_REASONS = new Set<RefundReason>([
  "duplicate",
  "fraudulent",
  "requested_by_customer",
]);

function parseRefundInput(body: unknown): RefundInput {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    throw new HttpError(400, "Request body must be an object.");
  }

  const { orderId, amountCents, reason } = body as Record<string, unknown>;

  if (typeof orderId !== "string" || orderId.trim() === "") {
    throw new HttpError(400, "orderId is required.");
  }

  if (
    typeof amountCents !== "number" ||
    !Number.isSafeInteger(amountCents) ||
    amountCents <= 0
  ) {
    throw new HttpError(
      400,
      "amountCents must be a positive integer representing the smallest currency unit.",
    );
  }

  if (typeof reason !== "string" || !ALLOWED_REASONS.has(reason as RefundReason)) {
    throw new HttpError(
      400,
      "reason must be duplicate, fraudulent, or requested_by_customer.",
    );
  }

  return {
    orderId,
    amountCents,
    reason: reason as RefundReason,
  };
}

function refundResponse(refund: {
  id: string;
  orderId: string;
  amountCents: number;
  reason: string;
  createdAt: Date;
  stripeRefundId: string | null;
  stripeStatus: string | null;
  status: RefundStatus;
}) {
  return {
    id: refund.id,
    orderId: refund.orderId,
    amountCents: refund.amountCents,
    reason: refund.reason,
    createdAt: refund.createdAt,
    stripeRefundId: refund.stripeRefundId,
    stripeStatus: refund.stripeStatus,
    status: refund.status,
  };
}

function assertSameRefundRequest(
  refund: {
    orderId: string;
    amountCents: number;
    reason: string;
    order: { tenantId: string };
  },
  input: RefundInput,
  tenantId: string,
) {
  if (
    refund.order.tenantId !== tenantId ||
    refund.orderId !== input.orderId ||
    refund.amountCents !== input.amountCents ||
    refund.reason !== input.reason
  ) {
    throw new HttpError(
      409,
      "Idempotency-Key was already used for a different refund request.",
    );
  }
}

export function buildRefundRouter(prisma: PrismaClient, stripe: Stripe): Router {
  const router = Router();

  router.post(
    "/",
    async (
      req: AuthenticatedRequest,
      res: Response,
      next: NextFunction,
    ): Promise<void> => {
      try {
        const session = req.session;
        if (!session?.userId || !session.tenantId) {
          throw new HttpError(401, "Authentication is required.");
        }

        const input = parseRefundInput(req.body);

        const idempotencyKey = req.header("Idempotency-Key")?.trim();
        if (!idempotencyKey || idempotencyKey.length > 255) {
          throw new HttpError(
            400,
            "A valid Idempotency-Key header (1-255 characters) is required.",
          );
        }

        const reserveRefund = async () =>
          prisma.$transaction(async (tx) => {
            const existing = await tx.refund.findUnique({
              where: { idempotencyKey },
              include: { order: true },
            });

            if (existing) {
              assertSameRefundRequest(existing, input, session.tenantId);
              return { refund: existing, created: false };
            }

            // Serializes refund reservations for this order, preventing concurrent
            // partial refunds from exceeding the order total.
            const lockedOrders = await tx.$queryRaw<{ id: string }[]>(
              Prisma.sql`
                SELECT "id"
                FROM "Order"
                WHERE "id" = ${input.orderId}
                  AND "tenantId" = ${session.tenantId}
                FOR UPDATE
              `,
            );

            if (lockedOrders.length === 0) {
              throw new HttpError(404, "Order not found.");
            }

            const order = await tx.order.findUniqueOrThrow({
              where: { id: input.orderId },
            });

            if (!order.stripePaymentIntentId) {
              throw new HttpError(
                409,
                "This order has no Stripe PaymentIntent available for refunding.",
              );
            }

            const reserved = await tx.refund.aggregate({
              where: {
                orderId: order.id,
                status: {
                  in: [RefundStatus.PENDING, RefundStatus.SUBMITTED],
                },
              },
              _sum: { amountCents: true },
            });

            const alreadyReserved = reserved._sum.amountCents ?? 0;

            if (alreadyReserved + input.amountCents > order.totalCents) {
              throw new HttpError(
                422,
                "Refund amount exceeds the remaining refundable balance.",
              );
            }

            const refund = await tx.refund.create({
              data: {
                orderId: order.id,
                amountCents: input.amountCents,
                reason: input.reason,
                idempotencyKey,
                status: RefundStatus.PENDING,
              },
              include: { order: true },
            });

            return { refund, created: true };
          });

        let reservation;
        try {
          reservation = await reserveRefund();
        } catch (error) {
          // A concurrent request may have created this idempotency key first.
          if (!(error instanceof Prisma.PrismaClientKnownRequestError) || error.code !== "P2002") {
            throw error;
          }

          const existing = await prisma.refund.findUnique({
            where: { idempotencyKey },
            include: { order: true },
          });

          if (!existing) throw error;

          assertSameRefundRequest(existing, input, session.tenantId);
          reservation = { refund: existing, created: false };
        }

        if (reservation.refund.status === RefundStatus.SUBMITTED) {
          res.status(200).json(refundResponse(reservation.refund));
          return;
        }

        if (reservation.refund.status === RefundStatus.FAILED) {
          throw new HttpError(
            409,
            "This refund previously failed. Use a new Idempotency-Key after resolving the failure.",
          );
        }

        let stripeRefund: Stripe.Refund;
        try {
          stripeRefund = await stripe.refunds.create(
            {
              payment_intent: reservation.refund.order.stripePaymentIntentId!,
              amount: reservation.refund.amountCents,
              reason: reservation.refund.reason as Stripe.RefundCreateParams.Reason,
              metadata: {
                orderId: reservation.refund.orderId,
                refundId: reservation.refund.id,
                tenantId: session.tenantId,
                requestedByUserId: session.userId,
              },
            },
            { idempotencyKey },
          );
        } catch {
          // Leave the reservation PENDING: network failures may still have reached
          // Stripe. Retrying with the same key is the safe recovery path.
          throw new HttpError(
            502,
            "Stripe refund submission could not be confirmed. Retry with the same Idempotency-Key.",
          );
        }

        const persistedRefund = await prisma.refund.update({
          where: { id: reservation.refund.id },
          data: {
            stripeRefundId: stripeRefund.id,
            stripeStatus: stripeRefund.status ?? null,
            status: RefundStatus.SUBMITTED,
          },
        });

        res
          .status(reservation.created ? 201 : 200)
          .json(refundResponse(persistedRefund));
      } catch (error) {
        if (error instanceof HttpError) {
          res.status(error.statusCode).json({ error: error.message });
          return;
        }

        next(error);
      }
    },
  );

  return router;
}
```

```ts
// Example wiring

import express from "express";
import { PrismaClient } from "@prisma/client";
import Stripe from "stripe";
import { buildRefundRouter } from "./routes/refunds";

const app = express();
const prisma = new PrismaClient();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

app.use(express.json());
app.use("/refunds", buildRefundRouter(prisma, stripe));
```

This reserves the refund before calling Stripe, uses Stripe idempotency for safe retries, locks the order while calculating refundable balance, and scopes every order lookup to the authenticated tenant.