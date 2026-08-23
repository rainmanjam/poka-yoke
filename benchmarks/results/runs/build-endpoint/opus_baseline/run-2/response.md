Building this the way a payments endpoint has to be built: the money math and the tenant scoping are enforced by the database, not by the handler remembering to check. Assumptions I made are listed at the end.

`★ Insight ─────────────────────────────────────`
- Three things can go wrong here that a straightforward implementation won't catch: refunding another tenant's order, refunding more than the order total under concurrency, and double-refunding when a client retries a timed-out request. All three are *silent* — they succeed and return 200.
- The fix for each is a constraint, not a check: a composite FK on `(orderId, tenantId)`, a `CHECK (refundedCents <= totalCents)`, and a unique index on `(tenantId, idempotencyKey)`.
- Stripe-then-DB ordering matters. I persist a `PENDING` row *before* calling Stripe, so a crash mid-call leaves a record to reconcile rather than money moved with nothing written down.
`─────────────────────────────────────────────────`

## 1. Prisma schema additions

```prisma
// prisma/schema.prisma

enum RefundStatus {
  PENDING    // row written, Stripe outcome not yet confirmed
  SUCCEEDED
  FAILED
}

enum RefundReason {
  DUPLICATE
  FRAUDULENT
  REQUESTED_BY_CUSTOMER
  OTHER  // not sent to Stripe; free text lives in reasonNote
}

model Order {
  id         String @id @default(uuid()) @db.Uuid
  tenantId   String @db.Uuid
  totalCents Int
  currency   String @db.Char(3)

  // --- added ---
  stripePaymentIntentId String? @unique
  /// Running total of money committed to refunds (PENDING + SUCCEEDED).
  /// Guarded by CHECK (refundedCents BETWEEN 0 AND totalCents) — see migration.
  refundedCents Int @default(0)

  refunds Refund[]

  // Required so Refund can carry a composite FK. This is the device that makes
  // "refund attached to another tenant's order" unrepresentable in the schema.
  @@unique([id, tenantId])
  @@index([tenantId])
}

model Refund {
  id          String   @id @default(uuid()) @db.Uuid
  orderId     String   @db.Uuid
  amountCents Int
  reason      RefundReason
  createdAt   DateTime @default(now())

  // --- added ---
  tenantId          String       @db.Uuid
  status            RefundStatus @default(PENDING)
  reasonNote        String?      @db.VarChar(500)
  idempotencyKey    String       @db.VarChar(255)
  stripeRefundId    String?      @unique
  requestFingerprint String      @db.Char(64) // sha256 of the canonical request
  requestedByUserId String       @db.Uuid
  failureCode       String?
  updatedAt         DateTime     @updatedAt

  // Composite FK: a Refund cannot point at an Order in a different tenant.
  order Order @relation(fields: [orderId, tenantId], references: [id, tenantId], onDelete: Restrict)

  @@unique([tenantId, idempotencyKey])
  @@index([orderId])
  @@index([tenantId, createdAt])
}
```

## 2. Migration

```sql
-- prisma/migrations/20260822120000_refund_safety/migration.sql

CREATE TYPE "RefundStatus" AS ENUM ('PENDING', 'SUCCEEDED', 'FAILED');
CREATE TYPE "RefundReason" AS ENUM ('DUPLICATE', 'FRAUDULENT', 'REQUESTED_BY_CUSTOMER', 'OTHER');

-- ---------- Order ----------
ALTER TABLE "Order"
  ADD COLUMN "stripePaymentIntentId" TEXT,
  ADD COLUMN "refundedCents" INTEGER NOT NULL DEFAULT 0;

-- Backfill the running total from refunds that already exist.
UPDATE "Order" o
SET "refundedCents" = COALESCE(sub.total, 0)
FROM (
  SELECT "orderId", SUM("amountCents")::int AS total
  FROM "Refund"
  GROUP BY "orderId"
) sub
WHERE o.id = sub."orderId";

-- If this fails, historical data already over-refunds and must be reconciled
-- before the constraint can be trusted. Failing loudly here is the point.
ALTER TABLE "Order"
  ADD CONSTRAINT "Order_refunded_within_total"
  CHECK ("refundedCents" >= 0 AND "refundedCents" <= "totalCents");

CREATE UNIQUE INDEX "Order_stripePaymentIntentId_key"
  ON "Order" ("stripePaymentIntentId");

ALTER TABLE "Order"
  ADD CONSTRAINT "Order_id_tenantId_key" UNIQUE ("id", "tenantId");

-- ---------- Refund ----------
ALTER TABLE "Refund"
  ADD COLUMN "tenantId" UUID,
  ADD COLUMN "status" "RefundStatus" NOT NULL DEFAULT 'PENDING',
  ADD COLUMN "reasonNote" VARCHAR(500),
  ADD COLUMN "idempotencyKey" VARCHAR(255),
  ADD COLUMN "stripeRefundId" TEXT,
  ADD COLUMN "requestFingerprint" CHAR(64),
  ADD COLUMN "requestedByUserId" UUID,
  ADD COLUMN "failureCode" TEXT,
  ADD COLUMN "updatedAt" TIMESTAMP(3);

-- Backfill: existing rows are historical fact, so they are SUCCEEDED, their
-- tenant comes from the order, and their idempotency key is synthesised from
-- the primary key (unique by construction, and never collides with a client key).
UPDATE "Refund" r
SET "tenantId"           = o."tenantId",
    "status"             = 'SUCCEEDED',
    "idempotencyKey"     = 'legacy:' || r.id::text,
    "requestFingerprint" = repeat('0', 64),
    "updatedAt"          = r."createdAt"
FROM "Order" o
WHERE o.id = r."orderId";

-- requestedByUserId has no historical source. Left nullable would let new code
-- forget it; instead use the all-zero sentinel and keep the column NOT NULL.
UPDATE "Refund"
SET "requestedByUserId" = '00000000-0000-0000-0000-000000000000'::uuid
WHERE "requestedByUserId" IS NULL;

ALTER TABLE "Refund"
  ALTER COLUMN "tenantId" SET NOT NULL,
  ALTER COLUMN "idempotencyKey" SET NOT NULL,
  ALTER COLUMN "requestFingerprint" SET NOT NULL,
  ALTER COLUMN "requestedByUserId" SET NOT NULL,
  ALTER COLUMN "updatedAt" SET NOT NULL;

-- reason: free text -> enum
ALTER TABLE "Refund" RENAME COLUMN "reason" TO "reason_legacy";
ALTER TABLE "Refund" ADD COLUMN "reason" "RefundReason";

UPDATE "Refund" SET
  "reason" = CASE lower(trim("reason_legacy"))
    WHEN 'duplicate'             THEN 'DUPLICATE'::"RefundReason"
    WHEN 'fraudulent'            THEN 'FRAUDULENT'::"RefundReason"
    WHEN 'requested_by_customer' THEN 'REQUESTED_BY_CUSTOMER'::"RefundReason"
    ELSE 'OTHER'::"RefundReason"
  END,
  "reasonNote" = CASE
    WHEN lower(trim("reason_legacy")) NOT IN
         ('duplicate', 'fraudulent', 'requested_by_customer')
    THEN left("reason_legacy", 500)
  END;

ALTER TABLE "Refund" ALTER COLUMN "reason" SET NOT NULL;
ALTER TABLE "Refund" DROP COLUMN "reason_legacy";

ALTER TABLE "Refund"
  ADD CONSTRAINT "Refund_amount_positive" CHECK ("amountCents" > 0);

CREATE UNIQUE INDEX "Refund_tenantId_idempotencyKey_key"
  ON "Refund" ("tenantId", "idempotencyKey");
CREATE UNIQUE INDEX "Refund_stripeRefundId_key"
  ON "Refund" ("stripeRefundId");
CREATE INDEX "Refund_orderId_idx"            ON "Refund" ("orderId");
CREATE INDEX "Refund_tenantId_createdAt_idx" ON "Refund" ("tenantId", "createdAt");

-- Replaces any plain FK on orderId. Tenant must match the order's tenant.
ALTER TABLE "Refund" DROP CONSTRAINT IF EXISTS "Refund_orderId_fkey";
ALTER TABLE "Refund"
  ADD CONSTRAINT "Refund_orderId_tenantId_fkey"
  FOREIGN KEY ("orderId", "tenantId")
  REFERENCES "Order" ("id", "tenantId")
  ON DELETE RESTRICT ON UPDATE CASCADE;
```

> On a large `Refund` table, split this: ship the nullable columns + backfill first, then `SET NOT NULL` and `CREATE UNIQUE INDEX CONCURRENTLY` in a follow-up migration. The single-file version above takes an `ACCESS EXCLUSIVE` lock for the length of the backfill.

## 3. Errors

```ts
// src/refunds/errors.ts

export type RefundErrorCode =
  | 'VALIDATION_FAILED'
  | 'IDEMPOTENCY_KEY_REQUIRED'
  | 'IDEMPOTENCY_KEY_REUSED'
  | 'ORDER_NOT_FOUND'
  | 'ORDER_NOT_REFUNDABLE'
  | 'AMOUNT_EXCEEDS_REMAINING'
  | 'STRIPE_REJECTED'
  | 'REFUND_PENDING_CONFIRMATION';

const STATUS: Record<RefundErrorCode, number> = {
  VALIDATION_FAILED: 400,
  IDEMPOTENCY_KEY_REQUIRED: 400,
  IDEMPOTENCY_KEY_REUSED: 409,
  ORDER_NOT_FOUND: 404,
  ORDER_NOT_REFUNDABLE: 422,
  AMOUNT_EXCEEDS_REMAINING: 409,
  STRIPE_REJECTED: 402,
  REFUND_PENDING_CONFIRMATION: 202,
};

export class RefundError extends Error {
  readonly httpStatus: number;

  constructor(
    readonly code: RefundErrorCode,
    message: string,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = 'RefundError';
    this.httpStatus = STATUS[code];
  }
}
```

## 4. Request contract

```ts
// src/refunds/dto.ts
import { createHash } from 'node:crypto';
import { z } from 'zod';
import { RefundReason } from '@prisma/client';

/** Stripe's amount ceiling; also stops a fat-fingered 1e9 from reaching the API. */
const MAX_REFUND_MINOR_UNITS = 99_999_999;

export const CreateRefundBody = z.object({
  orderId: z.string().uuid(),
  // Integer minor units only. `.int()` rejects 10.5 — a float here means the
  // caller is working in dollars and would refund 100x too little.
  amountCents: z.number().int().positive().max(MAX_REFUND_MINOR_UNITS),
  reason: z.enum(['duplicate', 'fraudulent', 'requested_by_customer', 'other']),
  reasonNote: z.string().trim().min(1).max(500).optional(),
}).strict()
  .refine((b) => b.reason !== 'other' || !!b.reasonNote, {
    message: 'reasonNote is required when reason is "other"',
    path: ['reasonNote'],
  });

export type CreateRefundBody = z.infer<typeof CreateRefundBody>;

export const REASON_TO_DB: Record<CreateRefundBody['reason'], RefundReason> = {
  duplicate: RefundReason.DUPLICATE,
  fraudulent: RefundReason.FRAUDULENT,
  requested_by_customer: RefundReason.REQUESTED_BY_CUSTOMER,
  other: RefundReason.OTHER,
};

/** Stripe only accepts these three; OTHER is deliberately omitted. */
export const REASON_TO_STRIPE: Partial<
  Record<RefundReason, 'duplicate' | 'fraudulent' | 'requested_by_customer'>
> = {
  [RefundReason.DUPLICATE]: 'duplicate',
  [RefundReason.FRAUDULENT]: 'fraudulent',
  [RefundReason.REQUESTED_BY_CUSTOMER]: 'requested_by_customer',
};

/**
 * Binds an idempotency key to the request it was first used with. Replaying the
 * key with a different amount is a client bug, and returning the *original*
 * refund would hide it. We 409 instead.
 */
export function fingerprint(tenantId: string, body: CreateRefundBody): string {
  return createHash('sha256')
    .update(JSON.stringify([tenantId, body.orderId, body.amountCents, body.reason]))
    .digest('hex');
}
```

## 5. Service

```ts
// src/refunds/service.ts
import { Prisma, PrismaClient, RefundStatus, type Refund } from '@prisma/client';
import Stripe from 'stripe';
import { RefundError } from './errors';
import { CreateRefundBody, REASON_TO_DB, REASON_TO_STRIPE, fingerprint } from './dto';

export interface Session {
  userId: string;
  tenantId: string;
}

export interface Deps {
  prisma: PrismaClient;
  stripe: Stripe;
  logger: { info(o: object, m: string): void; error(o: object, m: string): void };
}

export interface RefundView {
  id: string;
  orderId: string;
  amountCents: number;
  currency: string;
  reason: string;
  reasonNote: string | null;
  status: RefundStatus;
  stripeRefundId: string | null;
  createdAt: string;
}

const OVER_REFUND_CONSTRAINT = 'Order_refunded_within_total';

export async function createRefund(
  { prisma, stripe, logger }: Deps,
  session: Session,
  idempotencyKey: string,
  body: CreateRefundBody,
): Promise<RefundView> {
  const { tenantId, userId } = session;
  const fp = fingerprint(tenantId, body);

  // ---- 1. Replay path -----------------------------------------------------
  const existing = await prisma.refund.findUnique({
    where: { tenantId_idempotencyKey: { tenantId, idempotencyKey } },
    include: { order: { select: { currency: true, stripePaymentIntentId: true } } },
  });
  if (existing) {
    return replay({ prisma, stripe, logger }, existing, existing.order, fp);
  }

  // ---- 2. Reserve the money in Postgres, before touching Stripe -----------
  // Everything in here is one transaction so that the row we write and the
  // running total we bump either both land or neither does.
  let reserved: { refund: Refund; currency: string; paymentIntentId: string };
  try {
    reserved = await prisma.$transaction(async (tx) => {
      // Scoped by BOTH id and tenantId. A valid orderId from another tenant
      // returns null here, indistinguishable from a nonexistent order.
      const order = await tx.order.findUnique({
        where: { id_tenantId: { id: body.orderId, tenantId } },
        select: {
          currency: true,
          totalCents: true,
          refundedCents: true,
          stripePaymentIntentId: true,
        },
      });
      if (!order) {
        throw new RefundError('ORDER_NOT_FOUND', `Order ${body.orderId} not found`);
      }
      if (!order.stripePaymentIntentId) {
        throw new RefundError(
          'ORDER_NOT_REFUNDABLE',
          'Order has no captured Stripe payment to refund',
        );
      }

      // Friendly error for the common case. The CHECK constraint below is what
      // actually makes over-refunding impossible — this is just a better message.
      const remaining = order.totalCents - order.refundedCents;
      if (body.amountCents > remaining) {
        throw new RefundError(
          'AMOUNT_EXCEEDS_REMAINING',
          `Refund of ${body.amountCents} exceeds ${remaining} remaining on this order`,
          { remainingCents: remaining },
        );
      }

      const refund = await tx.refund.create({
        data: {
          tenantId,
          orderId: body.orderId,
          amountCents: body.amountCents,
          reason: REASON_TO_DB[body.reason],
          reasonNote: body.reasonNote ?? null,
          status: RefundStatus.PENDING,
          idempotencyKey,
          requestFingerprint: fp,
          requestedByUserId: userId,
        },
      });

      // Row-level lock + CHECK constraint. Two concurrent requests for the last
      // $50 serialize here; the second one violates the constraint and aborts.
      await tx.order.update({
        where: { id_tenantId: { id: body.orderId, tenantId } },
        data: { refundedCents: { increment: body.amountCents } },
      });

      return {
        refund,
        currency: order.currency,
        paymentIntentId: order.stripePaymentIntentId,
      };
    });
  } catch (err) {
    throw translateReserveError(err, prisma, tenantId, idempotencyKey, fp);
  }

  // ---- 3. Call Stripe (outside the transaction — never hold a DB lock
  //         across a network call to a third party) ---------------------------
  const { refund, currency, paymentIntentId } = reserved;
  let stripeRefund: Stripe.Refund;
  try {
    stripeRefund = await stripe.refunds.create(
      {
        payment_intent: paymentIntentId,
        amount: refund.amountCents,
        reason: REASON_TO_STRIPE[refund.reason],
        metadata: {
          refundId: refund.id,
          orderId: refund.orderId,
          tenantId,
          requestedByUserId: userId,
        },
      },
      // Derived from our own primary key, so a retry of THIS call — by us or by
      // a client replaying the key — returns the original Stripe refund rather
      // than moving money twice.
      { idempotencyKey: `refund_${refund.id}` },
    );
  } catch (err) {
    throw await handleStripeFailure({ prisma, logger }, refund, err);
  }

  const settled = await settle(prisma, refund, stripeRefund);
  return toView(settled, currency);
}

// ---------------------------------------------------------------------------

async function replay(
  { prisma, stripe, logger }: Omit<Deps, 'stripe'> & { stripe: Stripe },
  existing: Refund,
  order: { currency: string; stripePaymentIntentId: string | null },
  fp: string,
): Promise<RefundView> {
  if (existing.requestFingerprint !== fp) {
    throw new RefundError(
      'IDEMPOTENCY_KEY_REUSED',
      'This Idempotency-Key was already used with different request parameters',
      { originalRefundId: existing.id },
    );
  }
  if (existing.status !== RefundStatus.PENDING) {
    return toView(existing, order.currency);
  }

  // PENDING replay means a previous attempt died mid-flight. Re-issuing with
  // the same Stripe idempotency key is a read: Stripe returns the original
  // object if it was created, or creates it if the first call never landed.
  logger.info({ refundId: existing.id }, 'reconciling pending refund with Stripe');
  const stripeRefund = await stripe.refunds.create(
    {
      payment_intent: order.stripePaymentIntentId!,
      amount: existing.amountCents,
      reason: REASON_TO_STRIPE[existing.reason],
      metadata: { refundId: existing.id, orderId: existing.orderId },
    },
    { idempotencyKey: `refund_${existing.id}` },
  );
  return toView(await settle(prisma, existing, stripeRefund), order.currency);
}

async function settle(
  prisma: PrismaClient,
  refund: Refund,
  stripeRefund: Stripe.Refund,
): Promise<Refund> {
  // Stripe's `pending` (common for ACH/bank refunds) is NOT a failure — the
  // money is committed. Only `failed`/`canceled` release the reservation.
  if (stripeRefund.status === 'failed' || stripeRefund.status === 'canceled') {
    return releaseAndFail(
      prisma,
      refund,
      stripeRefund.failure_reason ?? stripeRefund.status ?? 'stripe_failed',
    );
  }

  return prisma.refund.update({
    where: { id: refund.id },
    data: {
      status:
        stripeRefund.status === 'succeeded'
          ? RefundStatus.SUCCEEDED
          : RefundStatus.PENDING,
      stripeRefundId: stripeRefund.id,
    },
  });
}

async function handleStripeFailure(
  { prisma, logger }: Pick<Deps, 'prisma' | 'logger'>,
  refund: Refund,
  err: unknown,
): Promise<RefundError> {
  const definitive =
    err instanceof Stripe.errors.StripeError &&
    (err.type === 'StripeInvalidRequestError' || err.type === 'StripeCardError');

  if (definitive) {
    // Stripe is certain no refund exists. Safe to give the money back to the
    // order's remaining balance.
    await releaseAndFail(prisma, refund, err.code ?? err.type);
    return new RefundError('STRIPE_REJECTED', err.message, { stripeCode: err.code });
  }

  // Timeout, connection error, 5xx: Stripe's state is UNKNOWN. Do not release
  // the reservation — that is how you double-refund. Leave the row PENDING for
  // the reconciler (or a client retry with the same key) to resolve.
  logger.error(
    { refundId: refund.id, err },
    'stripe outcome unknown; refund left PENDING for reconciliation',
  );
  return new RefundError(
    'REFUND_PENDING_CONFIRMATION',
    'Refund is being processed; retry with the same Idempotency-Key to confirm',
    { refundId: refund.id },
  );
}

function releaseAndFail(
  prisma: PrismaClient,
  refund: Refund,
  failureCode: string,
): Promise<Refund> {
  return prisma.$transaction(async (tx) => {
    const updated = await tx.refund.update({
      where: { id: refund.id },
      data: { status: RefundStatus.FAILED, failureCode },
    });
    await tx.order.update({
      where: { id_tenantId: { id: refund.orderId, tenantId: refund.tenantId } },
      data: { refundedCents: { decrement: refund.amountCents } },
    });
    return updated;
  });
}

async function translateReserveError(
  err: unknown,
  prisma: PrismaClient,
  tenantId: string,
  idempotencyKey: string,
  fp: string,
): Promise<never> | never {
  if (err instanceof RefundError) throw err;

  // Two requests with the same key raced past the findUnique above.
  if (
    err instanceof Prisma.PrismaClientKnownRequestError &&
    err.code === 'P2002' &&
    (err.meta?.target as string[] | undefined)?.includes('idempotencyKey')
  ) {
    throw new RefundError(
      'IDEMPOTENCY_KEY_REUSED',
      'A refund with this Idempotency-Key is already in flight; retry shortly',
    );
  }

  // The CHECK constraint fired: concurrent refunds together exceeded the total.
  // This is the last line of defence and it is expected to fire under load.
  if (
    err instanceof Error &&
    err.message.includes(OVER_REFUND_CONSTRAINT)
  ) {
    throw new RefundError(
      'AMOUNT_EXCEEDS_REMAINING',
      'Refund would exceed the order total (concurrent refund detected)',
    );
  }

  throw err;
}

function toView(r: Refund, currency: string): RefundView {
  return {
    id: r.id,
    orderId: r.orderId,
    amountCents: r.amountCents,
    currency,
    reason: r.reason,
    reasonNote: r.reasonNote,
    status: r.status,
    stripeRefundId: r.stripeRefundId,
    createdAt: r.createdAt.toISOString(),
  };
}
```

## 6. Handler / router

```ts
// src/refunds/router.ts
import { Router, type Request, type Response, type NextFunction } from 'express';
import { CreateRefundBody } from './dto';
import { RefundError } from './errors';
import { createRefund, type Deps, type Session } from './service';

// The session is the ONLY source of tenantId. Note that CreateRefundBody is
// .strict() — a client that sends `tenantId` in the body gets a 400, not a
// silently ignored field.
declare module 'express-serve-static-core' {
  interface Request {
    session?: Session;
  }
}

export function refundsRouter(deps: Deps): Router {
  const router = Router();

  router.post('/refunds', async (req: Request, res: Response, next: NextFunction) => {
    try {
      const session = req.session;
      if (!session) {
        return res.status(401).json({ error: { code: 'UNAUTHENTICATED' } });
      }

      const idempotencyKey = req.get('Idempotency-Key');
      if (!idempotencyKey || idempotencyKey.length > 255) {
        throw new RefundError(
          'IDEMPOTENCY_KEY_REQUIRED',
          'An Idempotency-Key header (<=255 chars) is required for POST /refunds',
        );
      }

      const parsed = CreateRefundBody.safeParse(req.body);
      if (!parsed.success) {
        throw new RefundError(
          'VALIDATION_FAILED',
          'Invalid request body',
          parsed.error.flatten(),
        );
      }

      const refund = await createRefund(deps, session, idempotencyKey, parsed.data);
      return res.status(201).json({ refund });
    } catch (err) {
      return next(err);
    }
  });

  return router;
}

export function refundErrorHandler(
  err: unknown,
  _req: Request,
  res: Response,
  next: NextFunction,
) {
  if (!(err instanceof RefundError)) return next(err);

  // 202 is a success shape, not an error shape: the refund exists and is pending.
  return res.status(err.httpStatus).json({
    error: { code: err.code, message: err.message, details: err.details },
  });
}
```

## 7. Tests that prove the constraints actually fire

```ts
// src/refunds/__tests__/refund-constraints.test.ts
import { PrismaClient, Prisma } from '@prisma/client';

const prisma = new PrismaClient();

describe('database devices', () => {
  it('rejects refundedCents above totalCents', async () => {
    const order = await seedOrder({ totalCents: 5_000, refundedCents: 4_000 });
    await expect(
      prisma.order.update({
        where: { id: order.id },
        data: { refundedCents: { increment: 1_001 } },
      }),
    ).rejects.toThrow(/Order_refunded_within_total/);

    // Near miss: exactly the remaining balance must succeed.
    await expect(
      prisma.order.update({
        where: { id: order.id },
        data: { refundedCents: { increment: 1_000 } },
      }),
    ).resolves.toMatchObject({ refundedCents: 5_000 });
  });

  it('rejects a refund whose tenantId does not match its order', async () => {
    const order = await seedOrder({ tenantId: TENANT_A });
    await expect(
      prisma.refund.create({
        data: {
          orderId: order.id,
          tenantId: TENANT_B, // <- the bug the composite FK exists to catch
          amountCents: 100,
          reason: 'DUPLICATE',
          idempotencyKey: 'k1',
          requestFingerprint: '0'.repeat(64),
          requestedByUserId: USER_B,
        },
      }),
    ).rejects.toBeInstanceOf(Prisma.PrismaClientKnownRequestError);
  });

  it('rejects a duplicate idempotency key within a tenant, allows it across tenants', async () => {
    await seedRefund({ tenantId: TENANT_A, idempotencyKey: 'same' });
    await expect(
      seedRefund({ tenantId: TENANT_A, idempotencyKey: 'same' }),
    ).rejects.toThrow(/Refund_tenantId_idempotencyKey_key/);
    await expect(
      seedRefund({ tenantId: TENANT_B, idempotencyKey: 'same' }),
    ).resolves.toBeDefined();
  });
});

describe('createRefund', () => {
  it('returns 404 for an order belonging to another tenant', async () => {
    const order = await seedOrder({ tenantId: TENANT_A, totalCents: 1_000 });
    await expect(
      createRefund(deps, { userId: USER_B, tenantId: TENANT_B }, 'k', {
        orderId: order.id, amountCents: 500, reason: 'duplicate',
      }),
    ).rejects.toMatchObject({ code: 'ORDER_NOT_FOUND' });
    expect(stripe.refunds.create).not.toHaveBeenCalled();
  });

  it('leaves the refund PENDING and does NOT release funds on a Stripe timeout', async () => {
    stripe.refunds.create.mockRejectedValue(
      new Stripe.errors.StripeConnectionError({ message: 'timeout' }),
    );
    const order = await seedOrder({ totalCents: 1_000 });
    await expect(call(order, 1_000)).rejects.toMatchObject({
      code: 'REFUND_PENDING_CONFIRMATION',
    });

    const [refund] = await prisma.refund.findMany({ where: { orderId: order.id } });
    expect(refund.status).toBe('PENDING');
    // The reservation must survive — releasing it here is how you double-refund.
    expect((await getOrder(order.id)).refundedCents).toBe(1_000);
  });

  it('releases funds when Stripe definitively rejects', async () => {
    stripe.refunds.create.mockRejectedValue(
      new Stripe.errors.StripeInvalidRequestError({
        message: 'charge_already_refunded', code: 'charge_already_refunded',
      }),
    );
    const order = await seedOrder({ totalCents: 1_000 });
    await expect(call(order, 1_000)).rejects.toMatchObject({ code: 'STRIPE_REJECTED' });
    expect((await getOrder(order.id)).refundedCents).toBe(0);
  });

  it('replaying a key with a different amount is a 409, not a silent replay', async () => {
    const order = await seedOrder({ totalCents: 1_000 });
    await call(order, 400, 'key-1');
    await expect(call(order, 900, 'key-1')).rejects.toMatchObject({
      code: 'IDEMPOTENCY_KEY_REUSED',
    });
    expect(stripe.refunds.create).toHaveBeenCalledTimes(1);
  });

  it('serialises concurrent refunds against the remaining balance', async () => {
    const order = await seedOrder({ totalCents: 1_000 });
    const results = await Promise.allSettled([
      call(order, 600, 'a'),
      call(order, 600, 'b'),
    ]);
    expect(results.filter((r) => r.status === 'fulfilled')).toHaveLength(1);
    expect((await getOrder(order.id)).refundedCents).toBe(600);
  });
});
```

## What I assumed

- **`Idempotency-Key` is required.** A refund endpoint without one double-refunds the first time a client times out and retries. If your existing clients can't send it, the alternative is deriving the key from `(orderId, amountCents, reason)` — but that then blocks two legitimate identical partial refunds, so I chose the explicit header.
- **`Order` needs `stripePaymentIntentId`.** The schema you gave has no link to Stripe, so there's nothing to refund against. Added it as nullable + unique; an order without one is `ORDER_NOT_REFUNDABLE` (422).
- **`refundedCents` is denormalized onto `Order`** rather than summed from `Refund` on each request. `SUM()` under concurrency needs `SERIALIZABLE` or an explicit `SELECT … FOR UPDATE`; a single guarded counter column gets the same safety from one `CHECK`.
- **`reason` became an enum.** Stripe accepts exactly three values; free text meant every non-matching string was silently dropped on the way to Stripe. `OTHER` keeps the prose in `reasonNote` and sends no reason.
- **Currency is not accepted from the client** — it's inherited from the PaymentIntent. A `currency` field in the request is a mismatch bug waiting to happen.

One decision worth your call: on a Stripe timeout I return **202 with the refund left `PENDING`** rather than 500. That's correct but it means you need a reconciler — a job that re-issues `stripe.refunds.create` with `refund_${id}` for rows `PENDING` older than ~5 minutes. Without it, those rows hold a balance reservation forever. If you'd rather not run that job, the alternative is handling `refund.updated` / `refund.failed` webhooks instead, which I'd lean toward since you likely already have a Stripe webhook endpoint.