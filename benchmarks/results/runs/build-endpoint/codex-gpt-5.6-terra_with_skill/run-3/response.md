Assumptions: Express, `zod`, UUID primary keys, and a required `Idempotency-Key` header. `Order` stores the Stripe PaymentIntent ID used for refunds.

```ts
// src/refunds.ts
import type { Request, Response, Router } from "express";
import { Prisma, PrismaClient, RefundReason, RefundStatus } from "@prisma/client";
import Stripe from "stripe";
import { z } from "zod";

type Session = {
  userId: string;
  tenantId: string;
};

type AuthenticatedRequest = Request & {
  session?: Session;
};

export class HttpError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const refundBodySchema = z
  .object({
    orderId: z.string().uuid(),
    amountCents: z.number().int().positive().max(100_000_000),
    reason: z.enum([
      RefundReason.duplicate,
      RefundReason.fraudulent,
      RefundReason.requested_by_customer,
    ]),
  })
  .strict();

const sessionSchema = z.object({
  userId: z.string().min(1).max(255),
  tenantId: z.string().uuid(),
});

const idempotencyKeySchema = z.string().trim().min(1).max(255);

function isSerializationFailure(error: unknown): boolean {
  return (
    error instanceof Prisma.PrismaClientKnownRequestError &&
    error.code === "P2034"
  );
}

async function serializableRetry<T>(
  prisma: PrismaClient,
  action: (tx: Prisma.TransactionClient) => Promise<T>,
): Promise<T> {
  let lastError: unknown;

  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return await prisma.$transaction(action, {
        isolationLevel: Prisma.TransactionIsolationLevel.Serializable,
        maxWait: 5_000,
        timeout: 30_000,
      });
    } catch (error) {
      lastError = error;
      if (!isSerializationFailure(error) || attempt === 2) throw error;
    }
  }

  throw lastError;
}

function reservationStatus(stripeStatus: Stripe.Refund.Status): RefundStatus {
  switch (stripeStatus) {
    case "succeeded":
      return RefundStatus.succeeded;
    case "failed":
      return RefundStatus.failed;
    case "canceled":
      return RefundStatus.canceled;
    case "requires_action":
      return RefundStatus.requires_action;
    case "pending":
    default:
      // An unknown future Stripe state remains reserved until reconciliation.
      return RefundStatus.pending;
  }
}

export function registerRefundRoutes(
  router: Router,
  dependencies: {
    prisma: PrismaClient;
    stripe: Stripe;
  },
): void {
  const { prisma, stripe } = dependencies;

  router.post(
    "/refunds",
    async (req: AuthenticatedRequest, res: Response): Promise<void> => {
      const session = sessionSchema.safeParse(req.session);
      if (!session.success) {
        throw new HttpError(401, "Authentication is required.");
      }

      const body = refundBodySchema.safeParse(req.body);
      if (!body.success) {
        throw new HttpError(400, "Invalid refund request.");
      }

      const idempotencyKey = idempotencyKeySchema.safeParse(
        req.get("Idempotency-Key"),
      );
      if (!idempotencyKey.success) {
        throw new HttpError(
          400,
          "A non-empty Idempotency-Key header of at most 255 characters is required.",
        );
      }

      const { userId, tenantId } = session.data;
      const { orderId, amountCents, reason } = body.data;

      const result = await serializableRetry(prisma, async (tx) => {
        // RLS is transaction-local, so a pooled connection cannot inherit another tenant.
        await tx.$executeRaw`
          SELECT set_config('app.tenant_id', ${tenantId}, true)
        `;

        // The row lock serializes all refund calculations for this order.
        // RLS makes another tenant's order invisible, producing the same 404.
        const orders = await tx.$queryRaw<
          Array<{
            id: string;
            totalCents: number;
            currency: string;
            stripePaymentIntentId: string | null;
          }>
        >`
          SELECT
            "id",
            "totalCents",
            "currency",
            "stripePaymentIntentId"
          FROM "Order"
          WHERE "id" = ${orderId}
          FOR UPDATE
        `;

        const order = orders[0];
        if (!order) {
          throw new HttpError(404, "Order not found.");
        }

        if (!order.stripePaymentIntentId) {
          throw new HttpError(
            409,
            "This order has no refundable Stripe payment.",
          );
        }

        const existing = await tx.refund.findUnique({
          where: {
            orderId_idempotencyKey: {
              orderId,
              idempotencyKey: idempotencyKey.data,
            },
          },
        });

        if (existing) {
          if (
            existing.amountCents !== amountCents ||
            existing.reason !== reason
          ) {
            throw new HttpError(
              409,
              "This Idempotency-Key was already used with different refund details.",
            );
          }

          return { refund: existing, replayed: true };
        }

        const reserved = await tx.refund.aggregate({
          where: {
            orderId,
            status: {
              in: [
                RefundStatus.pending,
                RefundStatus.requires_action,
                RefundStatus.succeeded,
              ],
            },
          },
          _sum: { amountCents: true },
        });

        const remainingCents =
          order.totalCents - (reserved._sum.amountCents ?? 0);

        if (amountCents > remainingCents) {
          throw new HttpError(422, "Refund amount exceeds the remaining balance.");
        }

        let stripeRefund: Stripe.Refund;
        try {
          stripeRefund = await stripe.refunds.create(
            {
              payment_intent: order.stripePaymentIntentId,
              amount: amountCents,
              reason,
              metadata: {
                orderId,
                tenantId,
                requestedByUserId: userId,
              },
            },
            { idempotencyKey: idempotencyKey.data },
          );
        } catch (error) {
          if (error instanceof Stripe.errors.StripeError) {
            throw new HttpError(422, "Stripe rejected the refund request.");
          }
          throw error;
        }

        const refund = await tx.refund.create({
          data: {
            orderId,
            amountCents,
            reason,
            idempotencyKey: idempotencyKey.data,
            stripeRefundId: stripeRefund.id,
            stripeStatus: stripeRefund.status,
            status: reservationStatus(stripeRefund.status),
          },
        });

        return { refund, replayed: false };
      });

      res.status(result.replayed ? 200 : 201).json(result.refund);
    },
  );
}
```

```prisma
// prisma/schema.prisma — relevant models/additions

enum RefundReason {
  duplicate
  fraudulent
  requested_by_customer
}

enum RefundStatus {
  pending
  requires_action
  succeeded
  failed
  canceled
}

model Order {
  id                    String   @id @default(uuid()) @db.Uuid
  tenantId              String   @db.Uuid
  totalCents            Int
  currency              String   @db.Char(3)
  stripePaymentIntentId String?  @unique
  refunds               Refund[]

  @@index([tenantId])
}

model Refund {
  id             String       @id @default(uuid()) @db.Uuid
  orderId        String       @db.Uuid
  amountCents    Int
  reason         RefundReason
  status         RefundStatus @default(pending)
  stripeStatus   String
  stripeRefundId String       @unique
  idempotencyKey String
  createdAt      DateTime     @default(now())

  order Order @relation(fields: [orderId], references: [id], onDelete: Restrict)

  @@unique([orderId, idempotencyKey])
  @@index([orderId, status])
}
```

```sql
-- prisma/migrations/20260822000000_add_refund_safety/migration.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TYPE "RefundReason" AS ENUM (
  'duplicate',
  'fraudulent',
  'requested_by_customer'
);

CREATE TYPE "RefundStatus" AS ENUM (
  'pending',
  'requires_action',
  'succeeded',
  'failed',
  'canceled'
);

ALTER TABLE "Order"
  ADD COLUMN "stripePaymentIntentId" TEXT;

CREATE UNIQUE INDEX "Order_stripePaymentIntentId_key"
  ON "Order"("stripePaymentIntentId");

ALTER TABLE "Refund"
  ALTER COLUMN "reason" TYPE "RefundReason"
  USING "reason"::"RefundReason",
  ADD COLUMN "status" "RefundStatus" NOT NULL DEFAULT 'pending',
  ADD COLUMN "stripeStatus" TEXT NOT NULL DEFAULT 'pending',
  ADD COLUMN "stripeRefundId" TEXT,
  ADD COLUMN "idempotencyKey" TEXT;

ALTER TABLE "Refund"
  ALTER COLUMN "stripeRefundId" SET NOT NULL,
  ALTER COLUMN "idempotencyKey" SET NOT NULL;

ALTER TABLE "Refund"
  ADD CONSTRAINT "Refund_orderId_fkey"
    FOREIGN KEY ("orderId") REFERENCES "Order"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE UNIQUE INDEX "Refund_stripeRefundId_key"
  ON "Refund"("stripeRefundId");

CREATE UNIQUE INDEX "Refund_orderId_idempotencyKey_key"
  ON "Refund"("orderId", "idempotencyKey");

CREATE INDEX "Refund_orderId_status_idx"
  ON "Refund"("orderId", "status");

-- The application database role must be non-superuser, NOBYPASSRLS, and not
-- own these tables. set_config(..., true) in the handler scopes this to one tx.
ALTER TABLE "Order" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "Order" FORCE ROW LEVEL SECURITY;

CREATE POLICY "order_tenant_isolation" ON "Order"
  USING ("tenantId" = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK ("tenantId" = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE "Refund" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "Refund" FORCE ROW LEVEL SECURITY;

CREATE POLICY "refund_tenant_isolation" ON "Refund"
  USING (
    EXISTS (
      SELECT 1
      FROM "Order"
      WHERE "Order"."id" = "Refund"."orderId"
        AND "Order"."tenantId" = current_setting('app.tenant_id', true)::uuid
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1
      FROM "Order"
      WHERE "Order"."id" = "Refund"."orderId"
        AND "Order"."tenantId" = current_setting('app.tenant_id', true)::uuid
    )
  );
```

The control devices are: tenant RLS plus session-derived scoping prevents cross-tenant refunds; the locked order row and reserved-refund aggregate prevent concurrent over-refunds; and the required, payload-bound idempotency key prevents duplicate refunds on retries. Stripe supports idempotent POSTs and the listed refund reasons. [Stripe refund API](https://docs.stripe.com/api/refunds/create?lang=curl) [Stripe idempotency](https://docs.stripe.com/api/idempotent_requests?lang=curl)

A Stripe webhook should subsequently update `Refund.status`/`stripeStatus` for asynchronous failures or cancellations; keeping `pending` refunds reserved is the safe default until that reconciliation occurs.