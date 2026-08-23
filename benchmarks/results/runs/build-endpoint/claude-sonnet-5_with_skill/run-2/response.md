Read the poka-yoke router → routed to **design** (writing a new payments interface — explicit trigger for money/auth-touching interfaces). I ran the misuse ritual before writing types, then built the endpoint so the highest-value mistakes don't compile or don't commit, rather than relying on care at the call site.

## Assumptions (stated so you can correct them)
- Express + Prisma + Postgres + Stripe Node SDK, session already populated by upstream auth middleware as `{ userId, tenantId }`.
- Stripe needs a charge/PaymentIntent to refund against, and `Order` as given has nowhere to put one — I added `Order.stripePaymentIntentId`. Without it, this endpoint is physically impossible to implement correctly; if it already exists elsewhere under a different name, drop that column from the migration and read the real one.
- `Refund.reason` was free text; I've constrained it to Stripe's three canonical values since a fourth, home-grown reason string would just crash the Stripe call at the boundary anyway.

## The misuse ritual (what actually shaped the design)
| # | Question | Answer that mattered |
|---|---|---|
| 1 | Swappable params? | `orderId`/`tenantId`/`userId` are all bare strings — one typo swaps them silently. |
| 4 | Second call? | A retried POST (client timeout, at-least-once queue, double-click) must not create a second Stripe refund. |
| 3 | Nonsense states? | A `Refund` with no idea whether Stripe actually succeeded is a real state today (network call outlives the request). |
| 5 | Worst input? | `amountCents` bigger than what's left on the order; `orderId` that belongs to a different tenant. |
| 6 | New case next year? | A new refund reason Stripe doesn't accept must fail to compile/typecheck, not fail at Stripe's API in production. |

---

### `prisma/schema.prisma` (additions/changes)

```prisma
enum RefundStatus {
  PENDING
  SUCCEEDED
  FAILED
}

enum RefundReason {
  DUPLICATE
  FRAUDULENT
  REQUESTED_BY_CUSTOMER
}

model Order {
  id                     String   @id @default(cuid())
  tenantId               String
  totalCents             Int
  currency               String
  // A refund is physically impossible without this — see migration note.
  stripePaymentIntentId  String?
  refunds                Refund[]

  @@index([tenantId])
}

model Refund {
  id             String       @id @default(cuid())
  orderId        String
  order          Order        @relation(fields: [orderId], references: [id])
  tenantId       String
  amountCents    Int
  reason         RefundReason
  status         RefundStatus @default(PENDING)
  // Required, not optional — an optional idempotency key is a suggestion.
  idempotencyKey String
  // Binds the key to the exact request body, so a reused key with a
  // different amount/orderId is rejected instead of silently replayed.
  payloadHash    String
  stripeRefundId String?      @unique
  failureReason  String?
  createdAt      DateTime     @default(now())
  updatedAt      DateTime     @updatedAt

  @@unique([tenantId, idempotencyKey])
  @@index([orderId])
  @@index([tenantId, status])
}
```

★ Insight ─────────────────────────────────────
`@@unique([tenantId, idempotencyKey])` rather than a global unique on `idempotencyKey` alone matters here: two different tenants' clients might both generate the key `"retry-1"`. Scoping the uniqueness to the tenant avoids a cross-tenant collision rejecting a legitimate request with a confusing 409.
─────────────────────────────────────────────────

### `prisma/migrations/20260822120000_add_refund_guardrails/migration.sql`

```sql
CREATE TYPE "RefundStatus" AS ENUM ('PENDING', 'SUCCEEDED', 'FAILED');
CREATE TYPE "RefundReason" AS ENUM ('DUPLICATE', 'FRAUDULENT', 'REQUESTED_BY_CUSTOMER');

-- Nullable for now — backfill existing orders, then a follow-up migration
-- should tighten this to NOT NULL (expand/contract; see hazard-catalog M7).
ALTER TABLE "Order" ADD COLUMN "stripePaymentIntentId" TEXT;
CREATE INDEX IF NOT EXISTS "Order_tenantId_idx" ON "Order"("tenantId");

-- If this table already holds rows, add these as nullable first, backfill,
-- then tighten to NOT NULL in a second migration — a single-step NOT NULL
-- ADD COLUMN will fail loudly against existing data, which is correct: it's
-- surfacing that the greenfield assumption doesn't hold, not a migration bug.
ALTER TABLE "Refund"
  ADD COLUMN "tenantId" TEXT NOT NULL,
  ADD COLUMN "status" "RefundStatus" NOT NULL DEFAULT 'PENDING',
  ADD COLUMN "idempotencyKey" TEXT NOT NULL,
  ADD COLUMN "payloadHash" TEXT NOT NULL,
  ADD COLUMN "stripeRefundId" TEXT,
  ADD COLUMN "failureReason" TEXT,
  ADD COLUMN "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- Constrains reason to values Stripe (and our domain) actually accept.
-- USING fails the migration if any existing row holds an unmapped value —
-- that failure is the point.
ALTER TABLE "Refund"
  ALTER COLUMN "reason" TYPE "RefundReason" USING ("reason"::"RefundReason");

-- Row-local invariant → belongs in the database, not just the handler.
ALTER TABLE "Refund" ADD CONSTRAINT "Refund_amountCents_positive" CHECK ("amountCents" > 0);

-- The one row per (tenant, idempotency key) constraint is what actually stops
-- a retried POST from producing a second Stripe refund. The application-level
-- check below just turns the failure into a clean 409 instead of a 500.
CREATE UNIQUE INDEX "Refund_tenantId_idempotencyKey_key" ON "Refund"("tenantId", "idempotencyKey");
CREATE UNIQUE INDEX "Refund_stripeRefundId_key" ON "Refund"("stripeRefundId");

CREATE INDEX "Refund_orderId_idx" ON "Refund"("orderId");
CREATE INDEX "Refund_tenantId_status_idx" ON "Refund"("tenantId", "status");
```

### `src/types/ids.ts`

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type TenantId = Brand<string, "TenantId">;
export type UserId = Brand<string, "UserId">;
export type OrderId = Brand<string, "OrderId">;
export type IdempotencyKey = Brand<string, "IdempotencyKey">;

export const TenantId = (value: string): TenantId => value as TenantId;
export const UserId = (value: string): UserId => value as UserId;
export const OrderId = (value: string): OrderId => value as OrderId;
export const IdempotencyKey = (value: string): IdempotencyKey => value as IdempotencyKey;
```

★ Insight ─────────────────────────────────────
Branding costs nothing at runtime — it's a phantom type that only exists for `tsc`. Without it, `session.tenantId` and `body.orderId` are both `string`, and a handler that accidentally does `findOrder(body.orderId, body.orderId)` compiles cleanly. With branding, that line is a type error the moment it's written.
─────────────────────────────────────────────────

### `src/types/session.ts`

```ts
import type { Request } from "express";
import type { TenantId, UserId } from "./ids";

export interface AuthenticatedSession {
  userId: UserId;
  tenantId: TenantId;
}

export interface RequestWithSession extends Request {
  session?: AuthenticatedSession;
}
```

### `src/lib/errors.ts`

```ts
export class AppError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export const Errors = {
  Unauthenticated: () =>
    new AppError(401, "unauthenticated", "Request has no authenticated session"),
  MissingIdempotencyKey: () =>
    new AppError(400, "missing_idempotency_key", "Idempotency-Key header is required"),
  OrderNotFound: () =>
    new AppError(404, "order_not_found", "Order not found"),
  IdempotencyKeyReused: () =>
    new AppError(
      409,
      "idempotency_key_reused",
      "Idempotency-Key was already used with a different request body",
    ),
  RefundInFlight: () =>
    new AppError(409, "refund_in_flight", "A refund with this Idempotency-Key is already processing"),
  AmountExceedsRemaining: (remainingCents: number) =>
    new AppError(
      422,
      "amount_exceeds_remaining",
      `amountCents exceeds the ${remainingCents} cents remaining on this order`,
    ),
  StripeFailure: (message: string) =>
    new AppError(502, "stripe_refund_failed", message),
};
```

### `src/lib/stripe.ts`

```ts
import Stripe from "stripe";

// Fail at module load, not on the one request that hits this path at 3am.
const secretKey = process.env.STRIPE_SECRET_KEY;
if (!secretKey) {
  throw new Error("STRIPE_SECRET_KEY is not set");
}

export const stripe = new Stripe(secretKey, {
  apiVersion: "2024-06-20",
});
```

### `src/lib/prisma.ts`

```ts
import { PrismaClient } from "@prisma/client";

export const prisma = new PrismaClient();
```

### `src/schemas/refund.ts`

```ts
import { z } from "zod";

export const RefundReasonSchema = z.enum([
  "DUPLICATE",
  "FRAUDULENT",
  "REQUESTED_BY_CUSTOMER",
]);

export const CreateRefundBodySchema = z.object({
  orderId: z.string().min(1, "orderId is required"),
  amountCents: z
    .number()
    .int("amountCents must be an integer number of cents")
    .positive("amountCents must be greater than zero")
    .max(100_000_000, "amountCents exceeds the maximum single refund size"),
  reason: RefundReasonSchema,
});
export type CreateRefundBody = z.infer<typeof CreateRefundBodySchema>;

export const IdempotencyKeyHeaderSchema = z
  .string()
  .min(8, "Idempotency-Key must be at least 8 characters")
  .max(255)
  .regex(/^[A-Za-z0-9._-]+$/, "Idempotency-Key has an invalid character");
```

### `src/routes/refunds.ts`

```ts
import { Router, type Response, type NextFunction } from "express";
import { createHash } from "node:crypto";
import { RefundStatus, type Refund } from "@prisma/client";
import type Stripe from "stripe";
import { prisma } from "../lib/prisma";
import { stripe } from "../lib/stripe";
import { AppError, Errors } from "../lib/errors";
import { OrderId, IdempotencyKey } from "../types/ids";
import type { RequestWithSession } from "../types/session";
import {
  CreateRefundBodySchema,
  IdempotencyKeyHeaderSchema,
  type CreateRefundBody,
} from "../schemas/refund";
import { ZodError } from "zod";

const STRIPE_REASON: Record<CreateRefundBody["reason"], Stripe.RefundCreateParams.Reason> = {
  DUPLICATE: "duplicate",
  FRAUDULENT: "fraudulent",
  REQUESTED_BY_CUSTOMER: "requested_by_customer",
};

function hashPayload(body: CreateRefundBody): string {
  return createHash("sha256")
    .update(JSON.stringify({ orderId: body.orderId, amountCents: body.amountCents, reason: body.reason }))
    .digest("hex");
}

function requireSession(req: RequestWithSession) {
  if (!req.session) throw Errors.Unauthenticated();
  return req.session;
}

function toApiRefund(refund: Refund) {
  return {
    id: refund.id,
    orderId: refund.orderId,
    amountCents: refund.amountCents,
    reason: refund.reason,
    status: refund.status,
    stripeRefundId: refund.stripeRefundId,
    createdAt: refund.createdAt,
  };
}

interface LockedOrderRow {
  id: string;
  totalCents: number;
  currency: string;
  stripePaymentIntentId: string | null;
}

async function createRefundHandler(req: RequestWithSession, res: Response, next: NextFunction) {
  try {
    const session = requireSession(req);

    const idempotencyKeyHeader = req.header("Idempotency-Key");
    if (!idempotencyKeyHeader) throw Errors.MissingIdempotencyKey();
    const idempotencyKey = IdempotencyKey(IdempotencyKeyHeaderSchema.parse(idempotencyKeyHeader));

    const body = CreateRefundBodySchema.parse(req.body);
    const orderId = OrderId(body.orderId);
    const payloadHash = hashPayload(body);

    const { refund, order } = await prisma.$transaction(async (tx) => {
      const existing = await tx.refund.findUnique({
        where: { tenantId_idempotencyKey: { tenantId: session.tenantId, idempotencyKey } },
      });

      if (existing && existing.payloadHash !== payloadHash) {
        throw Errors.IdempotencyKeyReused();
      }
      if (existing?.status === RefundStatus.PENDING) {
        throw Errors.RefundInFlight();
      }

      // FOR UPDATE serializes concurrent refund attempts on the same order,
      // so the "remaining balance" read below can't race with another one.
      // The tenantId filter here — not just orderId — is what makes a
      // cross-tenant orderId 404 identically to a nonexistent one.
      const orderRows = await tx.$queryRaw<LockedOrderRow[]>`
        SELECT id, "totalCents", currency, "stripePaymentIntentId"
        FROM "Order"
        WHERE id = ${orderId} AND "tenantId" = ${session.tenantId}
        FOR UPDATE
      `;
      const order = orderRows[0];
      if (!order) throw Errors.OrderNotFound();

      if (existing?.status === RefundStatus.SUCCEEDED) {
        return { refund: existing, order }; // replay, no new Stripe call
      }

      // PENDING rows count against the remaining balance too, not just
      // SUCCEEDED ones — otherwise two concurrent requests with different
      // idempotency keys could each pass this check before either commits.
      const reserved = await tx.refund.aggregate({
        where: {
          orderId,
          tenantId: session.tenantId,
          status: { in: [RefundStatus.PENDING, RefundStatus.SUCCEEDED] },
          ...(existing ? { NOT: { id: existing.id } } : {}),
        },
        _sum: { amountCents: true },
      });
      const remaining = order.totalCents - (reserved._sum.amountCents ?? 0);
      if (body.amountCents > remaining) {
        throw Errors.AmountExceedsRemaining(remaining);
      }

      const refund = existing
        ? await tx.refund.update({
            where: { id: existing.id },
            data: { status: RefundStatus.PENDING, failureReason: null },
          })
        : await tx.refund.create({
            data: {
              orderId,
              tenantId: session.tenantId,
              amountCents: body.amountCents,
              reason: body.reason,
              idempotencyKey,
              payloadHash,
              status: RefundStatus.PENDING,
            },
          });

      return { refund, order };
    });

    if (refund.status === RefundStatus.SUCCEEDED) {
      return res.status(200).json(toApiRefund(refund));
    }

    if (!order.stripePaymentIntentId) {
      await prisma.refund.update({
        where: { id: refund.id },
        data: { status: RefundStatus.FAILED, failureReason: "order_missing_payment_intent" },
      });
      throw Errors.StripeFailure("Order has no recorded Stripe payment intent");
    }

    let stripeRefund: Stripe.Refund;
    try {
      // Passing the same key to Stripe means even a crash between the DB
      // commit above and this call and a process retry can't double-refund
      // at Stripe's end either.
      stripeRefund = await stripe.refunds.create(
        {
          payment_intent: order.stripePaymentIntentId,
          amount: refund.amountCents,
          reason: STRIPE_REASON[refund.reason],
          metadata: { tenantId: session.tenantId, orderId, refundId: refund.id },
        },
        { idempotencyKey: `${session.tenantId}:${idempotencyKey}` },
      );
    } catch (err) {
      await prisma.refund.update({
        where: { id: refund.id },
        data: {
          status: RefundStatus.FAILED,
          failureReason: err instanceof Error ? err.message : "unknown_stripe_error",
        },
      });
      throw Errors.StripeFailure(err instanceof Error ? err.message : "Stripe refund failed");
    }

    const succeeded = await prisma.refund.update({
      where: { id: refund.id },
      data: { status: RefundStatus.SUCCEEDED, stripeRefundId: stripeRefund.id },
    });

    return res.status(200).json(toApiRefund(succeeded));
  } catch (err) {
    next(err);
  }
}

export function refundErrorHandler(err: unknown, _req: RequestWithSession, res: Response, next: NextFunction) {
  if (err instanceof AppError) {
    return res.status(err.status).json({ error: { code: err.code, message: err.message } });
  }
  if (err instanceof ZodError) {
    return res.status(400).json({ error: { code: "invalid_request", message: err.issues.map((i) => i.message).join("; ") } });
  }
  return next(err);
}

export const refundsRouter = Router();
refundsRouter.post("/refunds", createRefundHandler);
```

---

## Devices installed, and the rung each reaches

| Hazard | Device | Rung |
|---|---|---|
| Cross-tenant `orderId` (IDOR) | Order lookup filtered by `session.tenantId`, never a client-supplied value; miss and no-such-order return the identical 404 | Control |
| Retried POST double-charges | Required `Idempotency-Key` header + `@@unique([tenantId, idempotencyKey])`, key bound to a payload hash | Control |
| Over-refunding across concurrent requests | `SELECT ... FOR UPDATE` on the order row + summing PENDING+SUCCEEDED before insert | Control |
| Free-text `reason` reaching Stripe | Zod enum in the app, Postgres enum in the schema, both mirroring Stripe's 3 accepted values | Control |
| `amountCents` ≤ 0 or absurd | `CHECK (amountCents > 0)` in Postgres, upper bound in Zod | Control |
| Stripe call succeeds but the DB write is lost mid-crash | Row inserted as `PENDING` *before* calling Stripe, updated after | Control for the double-charge; **not** for the stuck-PENDING case below |
| Missing `STRIPE_SECRET_KEY` | Thrown at module load | Control |

## What I deliberately left open
- **Crash between Stripe success and the final `SUCCEEDED` update** leaves the row `PENDING` forever; a retry then hits `409 refund_in_flight` even though Stripe already refunded. Closing this needs a reconciliation job that polls Stripe by `metadata.refundId` and heals stale `PENDING` rows — a Detection-rung device I didn't build here since it's a background job, not part of the endpoint.
- The $1,000,000 cap on `amountCents` is a placeholder; tune it to your actual refund policy.
- I added `Order.stripePaymentIntentId` as a nullable column rather than backfilling — if `Order` already has rows, back-fill before tightening it to `NOT NULL`.