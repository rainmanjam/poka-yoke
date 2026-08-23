Assumptions: Express handler, trusted server-side session middleware, and a required `Idempotency-Key` header. `reason` is constrained to Stripe’s supported refund reasons.

```ts
// src/refunds/postRefund.ts
import { createHash } from "node:crypto";
import type { NextFunction, Request, Response } from "express";
import Stripe from "stripe";
import {
  Prisma,
  PrismaClient,
  Refund,
  RefundReason,
  RefundStatus,
} from "@prisma/client";

export type AuthenticatedRequest = Request & {
  session?: {
    userId: string;
    tenantId: string;
  };
};

type OrderId = string & { readonly __brand: "OrderId" };

type CreateRefundInput = {
  orderId: OrderId;
  amountCents: number;
  reason: RefundReason;
};

class HttpError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
  ) {
    super(code);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(value: unknown, field: string, maxLength: number): string {
  if (typeof value !== "string") {
    throw new HttpError(400, `${field}_must_be_a_string`);
  }

  const parsed = value.trim();
  if (parsed.length === 0 || parsed.length > maxLength) {
    throw new HttpError(400, `${field}_is_invalid`);
  }

  return parsed;
}

function parseRefundInput(body: unknown): CreateRefundInput {
  if (!isRecord(body)) {
    throw new HttpError(400, "invalid_json_body");
  }

  const expectedKeys = new Set(["orderId", "amountCents", "reason"]);
  if (
    Object.keys(body).length !== expectedKeys.size ||
    Object.keys(body).some((key) => !expectedKeys.has(key))
  ) {
    throw new HttpError(400, "body_must_contain_only_orderId_amountCents_and_reason");
  }

  const orderId = requiredString(body.orderId, "orderId", 255) as OrderId;

  if (
    typeof body.amountCents !== "number" ||
    !Number.isSafeInteger(body.amountCents) ||
    body.amountCents < 1 ||
    body.amountCents > 2_147_483_647
  ) {
    throw new HttpError(400, "amountCents_must_be_a_positive_integer");
  }

  if (
    body.reason !== RefundReason.duplicate &&
    body.reason !== RefundReason.fraudulent &&
    body.reason !== RefundReason.requested_by_customer
  ) {
    throw new HttpError(400, "reason_is_invalid");
  }

  return { orderId, amountCents: body.amountCents, reason: body.reason };
}

function requireSession(request: AuthenticatedRequest): {
  userId: string;
  tenantId: string;
} {
  const session = request.session;

  if (
    !session ||
    typeof session.userId !== "string" ||
    session.userId.length === 0 ||
    typeof session.tenantId !== "string" ||
    session.tenantId.length === 0
  ) {
    throw new HttpError(401, "authentication_required");
  }

  return session;
}

function requireIdempotencyKey(request: Request): string {
  const key = request.get("Idempotency-Key")?.trim();

  if (!key || !/^[A-Za-z0-9._-]{1,200}$/.test(key)) {
    throw new HttpError(
      400,
      "Idempotency-Key_header_is_required_and_must_match_[A-Za-z0-9._-]{1,200}",
    );
  }

  return key;
}

function stripeIdempotencyKey(tenantId: string, key: string): string {
  return createHash("sha256")
    .update(`refund:${tenantId}:${key}`)
    .digest("hex");
}

function stripeReason(reason: RefundReason):
  | "duplicate"
  | "fraudulent"
  | "requested_by_customer" {
  switch (reason) {
    case RefundReason.duplicate:
      return "duplicate";
    case RefundReason.fraudulent:
      return "fraudulent";
    case RefundReason.requested_by_customer:
      return "requested_by_customer";
  }
}

function statusFromStripe(status: string | null): RefundStatus {
  switch (status) {
    case "succeeded":
      return RefundStatus.SUCCEEDED;
    case "failed":
    case "canceled":
      return RefundStatus.FAILED;
    // Unknown or newly introduced Stripe states reserve funds safely.
    default:
      return RefundStatus.PENDING;
  }
}

async function withTenantTransaction<T>(
  prisma: PrismaClient,
  tenantId: string,
  fn: (tx: Prisma.TransactionClient) => Promise<T>,
): Promise<T> {
  return prisma.$transaction(
    async (tx) => {
      // Required by the RLS policies in the migration. LOCAL prevents pool leakage.
      await tx.$executeRaw`
        SELECT set_config('app.tenant_id', ${tenantId}, true)
      `;

      return fn(tx);
    },
    { isolationLevel: Prisma.TransactionIsolationLevel.Serializable },
  );
}

function assertSameIdempotentRequest(
  refund: Refund,
  input: CreateRefundInput,
): void {
  if (
    refund.orderId !== input.orderId ||
    refund.amountCents !== input.amountCents ||
    refund.reason !== input.reason
  ) {
    throw new HttpError(409, "idempotency_key_reused_with_different_refund_request");
  }
}

function isRetryableTransactionError(error: unknown): boolean {
  return (
    error instanceof Prisma.PrismaClientKnownRequestError &&
    (error.code === "P2034" || error.code === "P2002")
  );
}

async function reserveRefund(
  prisma: PrismaClient,
  session: { userId: string; tenantId: string },
  input: CreateRefundInput,
  idempotencyKey: string,
): Promise<{ refund: Refund; created: boolean }> {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return await withTenantTransaction(prisma, session.tenantId, async (tx) => {
        const existing = await tx.refund.findFirst({
          where: {
            tenantId: session.tenantId,
            idempotencyKey,
          },
        });

        if (existing) {
          assertSameIdempotentRequest(existing, input);
          return { refund: existing, created: false };
        }

        // Serializes every refund attempt for this order.
        const [order] = await tx.$queryRaw<
          Array<{
            id: string;
            totalCents: number;
            stripePaymentIntentId: string | null;
          }>
        >`
          SELECT "id", "totalCents", "stripePaymentIntentId"
          FROM "Order"
          WHERE "id" = ${input.orderId}
            AND "tenantId" = ${session.tenantId}
          FOR UPDATE
        `;

        // Deliberately 404s for both missing and cross-tenant orders.
        if (!order) {
          throw new HttpError(404, "order_not_found");
        }

        if (!order.stripePaymentIntentId) {
          throw new HttpError(409, "order_has_no_refundable_stripe_payment");
        }

        const [total] = await tx.$queryRaw<Array<{ reserved: bigint }>>`
          SELECT COALESCE(SUM("amountCents"), 0)::bigint AS "reserved"
          FROM "Refund"
          WHERE "tenantId" = ${session.tenantId}
            AND "orderId" = ${input.orderId}
            AND "status" IN ('PENDING', 'SUCCEEDED')
        `;

        const reservedCents = total?.reserved ?? 0n;
        if (
          reservedCents + BigInt(input.amountCents) >
          BigInt(order.totalCents)
        ) {
          throw new HttpError(422, "refund_amount_exceeds_remaining_order_balance");
        }

        const refund = await tx.refund.create({
          data: {
            tenantId: session.tenantId,
            orderId: input.orderId,
            requestedByUserId: session.userId,
            stripePaymentIntentId: order.stripePaymentIntentId,
            amountCents: input.amountCents,
            reason: input.reason,
            idempotencyKey,
            status: RefundStatus.PENDING,
          },
        });

        return { refund, created: true };
      });
    } catch (error) {
      if (attempt < 2 && isRetryableTransactionError(error)) {
        continue;
      }
      throw error;
    }
  }

  throw new HttpError(409, "refund_request_conflicted_too_many_times");
}

async function recordStripeOutcome(
  prisma: PrismaClient,
  tenantId: string,
  refundId: string,
  stripeRefund: Stripe.Refund,
): Promise<Refund> {
  return withTenantTransaction(prisma, tenantId, async (tx) => {
    // Do not overwrite a more recent webhook transition.
    await tx.refund.updateMany({
      where: {
        id: refundId,
        tenantId,
        status: RefundStatus.PENDING,
      },
      data: {
        stripeRefundId: stripeRefund.id,
        status: statusFromStripe(stripeRefund.status),
      },
    });

    const stored = await tx.refund.findFirst({
      where: { id: refundId, tenantId },
    });

    if (!stored) {
      throw new Error("refund_disappeared_after_stripe_response");
    }

    return stored;
  });
}

export function createPostRefundHandler(
  prisma: PrismaClient,
  stripe: Stripe,
) {
  return async function postRefund(
    request: AuthenticatedRequest,
    response: Response,
    next: NextFunction,
  ): Promise<void> {
    try {
      const session = requireSession(request);
      const input = parseRefundInput(request.body);
      const idempotencyKey = requireIdempotencyKey(request);

      const reservation = await reserveRefund(
        prisma,
        session,
        input,
        idempotencyKey,
      );

      if (reservation.refund.status === RefundStatus.SUCCEEDED) {
        response.status(200).json(reservation.refund);
        return;
      }

      if (reservation.refund.status === RefundStatus.FAILED) {
        response.status(409).json(reservation.refund);
        return;
      }

      let stripeRefund: Stripe.Refund;
      try {
        stripeRefund = await stripe.refunds.create(
          {
            payment_intent: reservation.refund.stripePaymentIntentId,
            amount: reservation.refund.amountCents,
            reason: stripeReason(reservation.refund.reason),
            metadata: {
              localRefundId: reservation.refund.id,
              orderId: reservation.refund.orderId,
              tenantId: reservation.refund.tenantId,
              requestedByUserId: reservation.refund.requestedByUserId,
            },
          },
          {
            idempotencyKey: stripeIdempotencyKey(session.tenantId, idempotencyKey),
          },
        );
      } catch {
        // Do not release the reserved amount: Stripe may have processed the request
        // even though this process did not receive its response. Retrying the same
        // Idempotency-Key safely replays the Stripe operation.
        response.status(502).json({
          error: "stripe_refund_outcome_unknown_retry_with_the_same_idempotency_key",
          refund: reservation.refund,
        });
        return;
      }

      const refund = await recordStripeOutcome(
        prisma,
        session.tenantId,
        reservation.refund.id,
        stripeRefund,
      );

      const status =
        refund.status === RefundStatus.SUCCEEDED
          ? reservation.created
            ? 201
            : 200
          : refund.status === RefundStatus.FAILED
            ? 409
            : 202;

      response.status(status).json(refund);
    } catch (error) {
      if (error instanceof HttpError) {
        response.status(error.status).json({ error: error.code });
        return;
      }

      next(error);
    }
  };
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
  PENDING
  SUCCEEDED
  FAILED
}

model Order {
  id                    String   @id @default(uuid())
  tenantId              String
  totalCents            Int
  currency              String
  stripePaymentIntentId String?  @unique
  refunds               Refund[]

  @@unique([id, tenantId])
  @@index([tenantId])
}

model Refund {
  id                    String       @id @default(uuid())
  tenantId              String
  orderId               String
  requestedByUserId     String
  stripePaymentIntentId String
  amountCents           Int
  reason                RefundReason
  status                RefundStatus @default(PENDING)
  idempotencyKey        String
  stripeRefundId        String?      @unique
  createdAt             DateTime     @default(now())
  updatedAt             DateTime     @updatedAt

  order Order @relation(
    fields: [orderId, tenantId],
    references: [id, tenantId],
    onDelete: Restrict,
    onUpdate: Cascade
  )

  @@unique([tenantId, idempotencyKey])
  @@index([tenantId, orderId, status])
}
```

```sql
-- prisma/migrations/20260822000000_add_refunds/migration.sql
-- Greenfield migration. The enum conversion intentionally fails if old free-form
-- reason values exist, forcing an explicit historical-data mapping.

CREATE TYPE "RefundReason" AS ENUM (
  'duplicate',
  'fraudulent',
  'requested_by_customer'
);

CREATE TYPE "RefundStatus" AS ENUM (
  'PENDING',
  'SUCCEEDED',
  'FAILED'
);

ALTER TABLE "Order"
  ADD COLUMN "stripePaymentIntentId" TEXT;

ALTER TABLE "Order"
  ADD CONSTRAINT "Order_id_tenantId_key" UNIQUE ("id", "tenantId");

CREATE UNIQUE INDEX "Order_stripePaymentIntentId_key"
  ON "Order" ("stripePaymentIntentId")
  WHERE "stripePaymentIntentId" IS NOT NULL;

ALTER TABLE "Refund"
  ALTER COLUMN "reason" TYPE "RefundReason"
    USING "reason"::"RefundReason",
  ADD COLUMN "tenantId" TEXT NOT NULL,
  ADD COLUMN "requestedByUserId" TEXT NOT NULL,
  ADD COLUMN "stripePaymentIntentId" TEXT NOT NULL,
  ADD COLUMN "status" "RefundStatus" NOT NULL DEFAULT 'PENDING',
  ADD COLUMN "idempotencyKey" TEXT NOT NULL,
  ADD COLUMN "stripeRefundId" TEXT,
  ADD COLUMN "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ADD CONSTRAINT "Refund_amountCents_positive"
    CHECK ("amountCents" > 0),
  ADD CONSTRAINT "Refund_idempotencyKey_format"
    CHECK ("idempotencyKey" ~ '^[A-Za-z0-9._-]{1,200}$'),
  ADD CONSTRAINT "Refund_orderId_tenantId_fkey"
    FOREIGN KEY ("orderId", "tenantId")
    REFERENCES "Order" ("id", "tenantId")
    ON DELETE RESTRICT
    ON UPDATE CASCADE;

CREATE UNIQUE INDEX "Refund_tenantId_idempotencyKey_key"
  ON "Refund" ("tenantId", "idempotencyKey");

CREATE UNIQUE INDEX "Refund_stripeRefundId_key"
  ON "Refund" ("stripeRefundId")
  WHERE "stripeRefundId" IS NOT NULL;

CREATE INDEX "Refund_tenantId_orderId_status_idx"
  ON "Refund" ("tenantId", "orderId", "status");

-- Database-enforced tenant isolation. The application role must not have BYPASSRLS.
ALTER TABLE "Order" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "Order" FORCE ROW LEVEL SECURITY;
ALTER TABLE "Refund" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "Refund" FORCE ROW LEVEL SECURITY;

CREATE POLICY "Order_tenant_isolation" ON "Order"
  USING ("tenantId" = current_setting('app.tenant_id', true))
  WITH CHECK ("tenantId" = current_setting('app.tenant_id', true));

CREATE POLICY "Refund_tenant_isolation" ON "Refund"
  USING ("tenantId" = current_setting('app.tenant_id', true))
  WITH CHECK ("tenantId" = current_setting('app.tenant_id', true));
```

The controls are deliberate: tenant RLS plus a composite foreign key prevent cross-tenant refund rows; row locking prevents concurrent over-refunds; the unique idempotency key and Stripe idempotency key prevent retry-driven duplicate refunds. Stripe’s external outcome cannot be made locally atomic, so uncertain calls remain `PENDING` and retain the reserved amount until the same key is retried or a Stripe webhook reconciles it.