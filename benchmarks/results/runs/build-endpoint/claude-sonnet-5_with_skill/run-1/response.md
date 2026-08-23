Read the poka-yoke router, then `design` and `authz` (this is a new payments endpoint with tenant scoping on the session — both apply, design for the shape, authz for the tenant boundary), plus the TypeScript devices reference and the hazard catalog for the money/idempotency/race vocabulary. Here's the misuse list I designed against, then the code.

**Misuses enumerated before writing signatures:**
1. `tenantId` must come from the session, never the request body — a client-supplied tenant is a cross-tenant write waiting to happen (authz).
2. A retried POST (double-click, client timeout-and-retry, load balancer replay) must not create a second Stripe refund — this is literally the double-charge shape already logged in today's session for this branch, just on the refund side instead of the charge side.
3. Two concurrent refund requests against the same order must not both pass an "amount ≤ remaining balance" check and jointly over-refund (check-then-act race).
4. A refund must never be issued for more than what's left on the order.
5. Stripe succeeding and the DB write failing (or vice versa) must not produce an untracked refund or a duplicate one on retry.
6. Reusing an idempotency key with a *different* amount/order/reason must be rejected, not silently served the old result.
7. `reason` is a closed set Stripe itself enforces — leaving it a bare string lets a typo pass validation and fail at the Stripe boundary instead of at ours.

---

### 1. `prisma/schema.prisma` (additions)

```prisma
enum RefundReason {
  duplicate
  fraudulent
  requested_by_customer
}

enum RefundStatus {
  pending
  succeeded
  failed
}

model Order {
  id                   String   @id @default(cuid())
  tenantId             String
  totalCents           Int
  currency             String
  stripePaymentIntentId String? // needed to tell Stripe what to refund; nullable for pre-existing rows that predate this column
  refunds              Refund[]

  @@index([tenantId])
}

model Refund {
  id             String       @id @default(cuid())
  orderId        String
  order          Order        @relation(fields: [orderId], references: [id])
  tenantId       String
  amountCents    Int
  reason         RefundReason
  status         RefundStatus @default(pending)
  idempotencyKey String
  stripeRefundId String?      @unique
  createdAt      DateTime     @default(now())
  updatedAt      DateTime     @updatedAt

  @@unique([tenantId, idempotencyKey])
  @@index([orderId, status])
}
```

★ Insight ─────────────────────────────────────
`tenantId` is denormalized onto `Refund` even though it's reachable via `order.tenantId`. That's deliberate: it lets the idempotency-key uniqueness constraint (`@@unique([tenantId, idempotencyKey])`) live on `Refund` directly instead of requiring a join, and it means a raw `psql` query or a future service can't accidentally read/write a refund without a tenant column staring back at it.
─────────────────────────────────────────────────

### 2. Migration (`prisma/migrations/<ts>_add_refund_workflow/migration.sql`)

Written as expand-only against tables that already have rows — no destructive DDL co-deployed with app code (M7):

```sql
-- CreateEnum
CREATE TYPE "RefundReason" AS ENUM ('duplicate', 'fraudulent', 'requested_by_customer');
CREATE TYPE "RefundStatus" AS ENUM ('pending', 'succeeded', 'failed');

-- AlterTable: Order gains the Stripe reference refunds need
ALTER TABLE "Order" ADD COLUMN "stripePaymentIntentId" TEXT;

-- AlterTable: Refund gains tenant scoping, idempotency, status, Stripe linkage
ALTER TABLE "Refund"
  ADD COLUMN "tenantId" TEXT,
  ADD COLUMN "status" "RefundStatus" NOT NULL DEFAULT 'pending',
  ADD COLUMN "idempotencyKey" TEXT,
  ADD COLUMN "stripeRefundId" TEXT,
  ADD COLUMN "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- Backfill tenantId from the parent order, then close the gap
UPDATE "Refund" r SET "tenantId" = o."tenantId" FROM "Order" o WHERE r."orderId" = o."id";
ALTER TABLE "Refund" ALTER COLUMN "tenantId" SET NOT NULL;

-- Backfill idempotencyKey for pre-existing rows (their own id is a safe unique placeholder)
UPDATE "Refund" SET "idempotencyKey" = "id" WHERE "idempotencyKey" IS NULL;
ALTER TABLE "Refund" ALTER COLUMN "idempotencyKey" SET NOT NULL;

CREATE UNIQUE INDEX "Refund_tenantId_idempotencyKey_key" ON "Refund"("tenantId", "idempotencyKey");
CREATE UNIQUE INDEX "Refund_stripeRefundId_key" ON "Refund"("stripeRefundId");
CREATE INDEX "Refund_orderId_status_idx" ON "Refund"("orderId", "status");

ALTER TABLE "Refund" ADD CONSTRAINT "Refund_amountCents_positive" CHECK ("amountCents" > 0);
ALTER TABLE "Refund" ADD CONSTRAINT "Refund_orderId_fkey"
  FOREIGN KEY ("orderId") REFERENCES "Order"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
```

The positive-amount `CHECK` and the `(tenantId, idempotencyKey)` unique index aren't expressible in `schema.prisma` (Prisma has no `@check`), so they're hand-added here — this is F6 from the hazard catalog: push the invariant into the schema so it holds even for a script or a raw `psql` session, not just the code path below.

### 3. `src/lib/branded-types.ts`

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type TenantId = Brand<string, "TenantId">;
export type UserId = Brand<string, "UserId">;
export type OrderId = Brand<string, "OrderId">;
export type IdempotencyKey = Brand<string, "IdempotencyKey">;
export type Cents = Brand<number, "Cents">;
```

### 4. `src/refunds/refunds.schema.ts`

```ts
import { z } from "zod";
import type { Cents, IdempotencyKey, OrderId } from "../lib/branded-types";

export const RefundReasonSchema = z.enum([
  "duplicate",
  "fraudulent",
  "requested_by_customer",
]);

// Matches Stripe's own refund.reason enum exactly. If the business ever wants
// reasons Stripe doesn't recognize, that needs an explicit mapping function
// with an exhaustive switch — not attempted here, since today the two sets
// are identical and a mapping layer for a 1:1 passthrough is pure ceremony.
export type RefundReason = z.infer<typeof RefundReasonSchema>;

export const RefundRequestBodySchema = z.object({
  orderId: z.string().min(1).transform((s) => s as OrderId),
  amountCents: z.number().int().positive().transform((n) => n as Cents),
  reason: RefundReasonSchema,
});

export const IdempotencyKeyHeaderSchema = z
  .string()
  .min(1)
  .max(255)
  .transform((s) => s as IdempotencyKey);
```

### 5. `src/refunds/refunds.errors.ts`

```ts
export class RefundError extends Error {
  constructor(public readonly statusCode: number, message: string) {
    super(message);
  }
}
```

### 6. `src/refunds/refunds.service.ts`

```ts
import type Stripe from "stripe";
import type { PrismaClient, Refund } from "@prisma/client";
import type { Cents, IdempotencyKey, OrderId, TenantId } from "../lib/branded-types";
import type { RefundReason } from "./refunds.schema";
import { RefundError } from "./refunds.errors";

export interface CreateRefundParams {
  tenantId: TenantId;
  orderId: OrderId;
  amountCents: Cents;
  reason: RefundReason;
  idempotencyKey: IdempotencyKey;
}

export function makeCreateRefund(prisma: PrismaClient, stripe: Stripe) {
  return async function createRefund(params: CreateRefundParams): Promise<Refund> {
    const { tenantId, orderId, amountCents, reason, idempotencyKey } = params;

    // Step 1 — short transaction: lock the order row, check the running
    // total, reserve a "pending" row. No network call happens in here, so
    // the lock is never held across Stripe's latency.
    const step1 = await prisma.$transaction(async (tx) => {
      const [order] = await tx.$queryRaw<
        Array<{ id: string; totalCents: number; stripePaymentIntentId: string | null }>
      >`
        SELECT "id", "totalCents", "stripePaymentIntentId"
        FROM "Order"
        WHERE "id" = ${orderId} AND "tenantId" = ${tenantId}
        FOR UPDATE
      `;
      if (!order) {
        throw new RefundError(404, "order not found");
      }
      if (!order.stripePaymentIntentId) {
        throw new RefundError(422, "order has no recorded payment to refund");
      }

      const existing = await tx.refund.findUnique({
        where: { tenantId_idempotencyKey: { tenantId, idempotencyKey } },
      });
      if (existing) {
        if (
          existing.orderId !== orderId ||
          existing.amountCents !== amountCents ||
          existing.reason !== reason
        ) {
          throw new RefundError(409, "Idempotency-Key was already used for a different request");
        }
        return { kind: "replay" as const, refund: existing };
      }

      const reserved = await tx.refund.aggregate({
        where: { orderId, tenantId, status: { in: ["pending", "succeeded"] } },
        _sum: { amountCents: true },
      });
      const alreadyReserved = reserved._sum.amountCents ?? 0;
      if (alreadyReserved + amountCents > order.totalCents) {
        throw new RefundError(422, "refund would exceed the order total");
      }

      const created = await tx.refund.create({
        data: { orderId, tenantId, amountCents, reason, idempotencyKey, status: "pending" },
      });
      return {
        kind: "created" as const,
        refund: created,
        stripePaymentIntentId: order.stripePaymentIntentId,
      };
    });

    if (step1.kind === "replay") {
      return step1.refund;
    }

    // Step 2 — call Stripe outside the transaction, using the same
    // idempotency key. A retry that reaches this line twice (process crash,
    // client resend) gets Stripe's own idempotent replay instead of a
    // second refund.
    let stripeRefund: Stripe.Refund;
    try {
      stripeRefund = await stripe.refunds.create(
        {
          payment_intent: step1.stripePaymentIntentId,
          amount: amountCents,
          reason,
        },
        { idempotencyKey },
      );
    } catch (err) {
      await prisma.refund.update({
        where: { id: step1.refund.id },
        data: { status: "failed" },
      });
      throw new RefundError(502, "stripe refund failed");
    }

    return prisma.refund.update({
      where: { id: step1.refund.id },
      data: {
        status: stripeRefund.status === "failed" ? "failed" : "succeeded",
        stripeRefundId: stripeRefund.id,
      },
    });
  };
}
```

★ Insight ─────────────────────────────────────
The `FOR UPDATE` lock is on the **Order** row, not the Refund rows being inserted — that's what serializes two *different* idempotency keys racing on the same order (a legitimate double-submit of separate refunds), while the unique index on `(tenantId, idempotencyKey)` handles the *same* key arriving twice. Two separate devices for two separate hazards: one is a race (M5, needs atomicity), the other is a retry (M2, needs a required key plus a constraint).
─────────────────────────────────────────────────

### 7. `src/refunds/refunds.handler.ts`

```ts
import type { Request, Response } from "express";
import type { TenantId, UserId } from "../lib/branded-types";
import { RefundRequestBodySchema, IdempotencyKeyHeaderSchema } from "./refunds.schema";
import { RefundError } from "./refunds.errors";
import type { makeCreateRefund } from "./refunds.service";

interface Session {
  userId: string;
  tenantId: string;
}

function requireSession(req: Request): { userId: UserId; tenantId: TenantId } {
  const session = (req as Request & { session?: Session }).session;
  if (!session?.userId || !session?.tenantId) {
    throw new RefundError(401, "unauthenticated");
  }
  return { userId: session.userId as UserId, tenantId: session.tenantId as TenantId };
}

export function makeCreateRefundHandler(createRefund: ReturnType<typeof makeCreateRefund>) {
  return async function createRefundHandler(req: Request, res: Response): Promise<void> {
    try {
      const { tenantId } = requireSession(req);

      const keyResult = IdempotencyKeyHeaderSchema.safeParse(req.header("Idempotency-Key"));
      if (!keyResult.success) {
        res.status(400).json({ error: "Idempotency-Key header is required" });
        return;
      }

      const bodyResult = RefundRequestBodySchema.safeParse(req.body);
      if (!bodyResult.success) {
        res.status(400).json({ error: bodyResult.error.format() });
        return;
      }

      const refund = await createRefund({
        tenantId,
        orderId: bodyResult.data.orderId,
        amountCents: bodyResult.data.amountCents,
        reason: bodyResult.data.reason,
        idempotencyKey: keyResult.data,
      });

      res.status(201).json({ refund });
    } catch (err) {
      if (err instanceof RefundError) {
        res.status(err.statusCode).json({ error: err.message });
        return;
      }
      throw err;
    }
  };
}
```

### 8. Route wiring

```ts
import { Router } from "express";
import { prisma } from "../lib/prisma";
import { stripe } from "../lib/stripe";
import { makeCreateRefund } from "./refunds.service";
import { makeCreateRefundHandler } from "./refunds.handler";

export const refundsRouter = Router();
refundsRouter.post("/refunds", makeCreateRefundHandler(makeCreateRefund(prisma, stripe)));
```

---

**Where this lands on the ladder, and what's left open:**

- **Control**: tenant is read only from the session, never the body, and every order lookup is scoped by `tenantId` in the same query — an unscoped read isn't reachable from this handler (`authz`, source inspection).
- **Control**: `Idempotency-Key` is a required header, backed by a unique `(tenantId, idempotencyKey)` index, and a reused key with a different payload is rejected (409) rather than silently replayed — closes the exact double-charge shape from this session's earlier incident, on the refund side.
- **Control**: the over-refund check and the pending-row reservation happen inside one transaction holding a row lock on the order, so two concurrent refund requests can't both pass the balance check (M5). The positive-amount `CHECK` constraint holds even for a raw SQL client.
- **Left open, on purpose**: a refund that reaches `pending` and then crashes before the Stripe call resolves has no automatic resolver here — it needs a reconciliation job (Detection rung) that either replays the Stripe call with the same idempotency key or marks it failed after a timeout. I didn't build that worker because the handler alone was in scope, but a stuck `pending` row is the honest cost of not holding the DB lock across the Stripe network call — the alternative (lock held during the call) trades a small chance of a stuck row for a much larger chance of lock-timeout storms in production, so I took the trade deliberately rather than by omission.