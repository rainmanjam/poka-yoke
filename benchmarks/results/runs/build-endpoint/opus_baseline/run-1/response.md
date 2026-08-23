Using poka-yoke:design. Before the code, the misuse enumeration it asks for — because two items change the schema you gave me:

**Misuses I designed against**

| # | Misuse | Where it's stopped |
|---|---|---|
| 1 | `orderId` from tenant A refunded by tenant B | Order looked up by composite `(id, tenantId)`; `Refund` carries `tenantId` with a composite FK, so a cross-tenant row is unrepresentable in Postgres |
| 2 | Retry / double-click / at-least-once queue refunds twice | Required `Idempotency-Key` header → `UNIQUE(tenantId, idempotencyKey)`; plus a stable per-row key sent to Stripe |
| 3 | Refund more than the order is worth | `Order.refundedCents` running total + `CHECK (refundedCents <= totalCents)` — holds against `psql`, scripts, and other services, not just this handler |
| 4 | Concurrent partial refunds each pass a read-then-write check (TOCTOU) | The reserve is a single `UPDATE ... SET refundedCents = refundedCents + n`; row lock serializes, CHECK rejects the loser |
| 5 | Stripe succeeds, DB write dies → money out, no record | Reserve-then-call-then-settle. A crash leaves a `PENDING` row, never a silent loss |
| 6 | Stripe times out, caller retries, two real refunds | Indeterminate errors **do not** release the reservation. Only terminal ones do |
| 7 | `amountCents` and `totalCents` swapped, or a client-supplied `currency` disagreeing with the order | Branded `MinorUnits`; currency is never accepted from the client, only read from the order |
| 8 | New `RefundStatus` added later, some switch silently falls through | `assertNever` on every match |

**Two things about the spec I have to flag, then I build:** your `Refund(id, orderId, amountCents, reason, createdAt)` has nowhere to put Stripe's refund ID and no status — so a refund that Stripe accepted but your process died mid-write is invisible and unreconcilable. And `Order` has no `stripePaymentIntentId`, so there's nothing to call Stripe *with*. Both are additive migrations below.

---

`★ Insight ─────────────────────────────────────`
The ordering here is the whole design. The naive version is *call Stripe → write row*, which loses money on a crash. The version that looks safer — *write row → call Stripe → mark done* — is only safe if you also decide what "Stripe timed out" means. Releasing the reservation on a timeout is the double-refund bug: you don't know whether the money moved. So the code distinguishes **terminal** failures (Stripe definitely didn't act — release) from **indeterminate** ones (leave `PENDING`, return 202, let a reconciler ask Stripe).
`─────────────────────────────────────────────────`

## 1. `prisma/schema.prisma` — additions

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
  OTHER
}

model Order {
  id         String @id @default(cuid())
  tenantId   String
  totalCents Int
  currency   String @db.Char(3)

  // --- additions ---
  stripePaymentIntentId String? @unique
  /// Running total of reserved+settled refunds. Guarded by a CHECK constraint
  /// (Order_refundedCents_within_total) so over-refunding is impossible at the
  /// database layer, not just in this service.
  refundedCents Int @default(0)

  refunds Refund[]

  /// Target for Refund's composite FK. This is the device that makes a
  /// cross-tenant refund row unrepresentable.
  @@unique([id, tenantId])
  @@index([tenantId])
}

model Refund {
  id          String       @id @default(cuid())
  orderId     String
  amountCents Int
  reason      RefundReason
  createdAt   DateTime     @default(now())

  // --- additions ---
  tenantId       String
  note           String?
  status         RefundStatus @default(PENDING)
  idempotencyKey String
  stripeRefundId String?      @unique
  failureCode    String?
  updatedAt      DateTime     @updatedAt

  order Order @relation(fields: [orderId, tenantId], references: [id, tenantId], onDelete: Restrict)

  @@unique([tenantId, idempotencyKey])
  @@index([status, createdAt]) // reconciler sweep
  @@index([orderId])
}
```

## 2. `prisma/migrations/20260822_refunds_devices/migration.sql`

```sql
-- Additive migration over existing Order and Refund tables.
-- Backfills BEFORE constraints, so the CHECK is meaningful for historical rows.

BEGIN;

CREATE TYPE "RefundStatus" AS ENUM ('PENDING', 'SUCCEEDED', 'FAILED');
CREATE TYPE "RefundReason" AS ENUM ('DUPLICATE', 'FRAUDULENT', 'REQUESTED_BY_CUSTOMER', 'OTHER');

--------------------------------------------------------------------------------
-- Order
--------------------------------------------------------------------------------
ALTER TABLE "Order"
  ADD COLUMN "stripePaymentIntentId" TEXT,
  ADD COLUMN "refundedCents"         INTEGER NOT NULL DEFAULT 0;

-- Backfill the running total from refunds that already exist.
UPDATE "Order" o
SET "refundedCents" = s.total
FROM (
  SELECT "orderId", SUM("amountCents")::INTEGER AS total
  FROM "Refund"
  GROUP BY "orderId"
) s
WHERE s."orderId" = o."id";

-- The ceiling. If this ALTER fails, you have pre-existing over-refunded orders:
-- that is the constraint doing its job on day one. Find them with
--   SELECT id FROM "Order" WHERE "refundedCents" > "totalCents";
-- and reconcile before re-running.
ALTER TABLE "Order"
  ADD CONSTRAINT "Order_refundedCents_within_total"
  CHECK ("refundedCents" >= 0 AND "refundedCents" <= "totalCents");

CREATE UNIQUE INDEX "Order_stripePaymentIntentId_key" ON "Order" ("stripePaymentIntentId");
CREATE UNIQUE INDEX "Order_id_tenantId_key"           ON "Order" ("id", "tenantId");
CREATE INDEX IF NOT EXISTS "Order_tenantId_idx"       ON "Order" ("tenantId");

--------------------------------------------------------------------------------
-- Refund
--------------------------------------------------------------------------------
ALTER TABLE "Refund"
  ADD COLUMN "tenantId"       TEXT,
  ADD COLUMN "note"           TEXT,
  ADD COLUMN "status"         "RefundStatus" NOT NULL DEFAULT 'SUCCEEDED',
  ADD COLUMN "idempotencyKey" TEXT,
  ADD COLUMN "stripeRefundId" TEXT,
  ADD COLUMN "failureCode"    TEXT,
  ADD COLUMN "updatedAt"      TIMESTAMP(3);

-- reason: free text -> closed enum, preserving the original string in `note`.
ALTER TABLE "Refund" RENAME COLUMN "reason" TO "reason_legacy";
ALTER TABLE "Refund" ADD COLUMN "reason" "RefundReason";

UPDATE "Refund" SET "reason" =
  CASE lower(btrim(COALESCE("reason_legacy", '')))
    WHEN 'duplicate'             THEN 'DUPLICATE'::"RefundReason"
    WHEN 'fraudulent'            THEN 'FRAUDULENT'::"RefundReason"
    WHEN 'requested_by_customer' THEN 'REQUESTED_BY_CUSTOMER'::"RefundReason"
    ELSE 'OTHER'::"RefundReason"
  END;

UPDATE "Refund" SET "note" = "reason_legacy"
WHERE "reason" = 'OTHER' AND "reason_legacy" IS NOT NULL;

UPDATE "Refund" r SET "tenantId" = o."tenantId" FROM "Order" o WHERE o."id" = r."orderId";
UPDATE "Refund" SET "idempotencyKey" = 'legacy:' || "id" WHERE "idempotencyKey" IS NULL;
UPDATE "Refund" SET "updatedAt" = "createdAt" WHERE "updatedAt" IS NULL;

ALTER TABLE "Refund"
  DROP COLUMN "reason_legacy",
  ALTER COLUMN "reason"         SET NOT NULL,
  ALTER COLUMN "tenantId"       SET NOT NULL,
  ALTER COLUMN "idempotencyKey" SET NOT NULL,
  ALTER COLUMN "updatedAt"      SET NOT NULL,
  ALTER COLUMN "status"         SET DEFAULT 'PENDING';

ALTER TABLE "Refund"
  ADD CONSTRAINT "Refund_amountCents_positive" CHECK ("amountCents" > 0);

-- Replace the single-column FK with a composite one. A Refund row can now only
-- reference an Order that agrees with it about the tenant.
ALTER TABLE "Refund" DROP CONSTRAINT IF EXISTS "Refund_orderId_fkey";
ALTER TABLE "Refund"
  ADD CONSTRAINT "Refund_orderId_tenantId_fkey"
  FOREIGN KEY ("orderId", "tenantId") REFERENCES "Order" ("id", "tenantId")
  ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE UNIQUE INDEX "Refund_tenantId_idempotencyKey_key" ON "Refund" ("tenantId", "idempotencyKey");
CREATE UNIQUE INDEX "Refund_stripeRefundId_key"          ON "Refund" ("stripeRefundId");
CREATE INDEX        "Refund_status_createdAt_idx"        ON "Refund" ("status", "createdAt");
CREATE INDEX IF NOT EXISTS "Refund_orderId_idx"          ON "Refund" ("orderId");

COMMIT;
```

## 3. `src/domain/branded.ts`

```ts
declare const brand: unique symbol;
type Brand<T, B extends string> = T & { readonly [brand]: B };

export type TenantId = Brand<string, 'TenantId'>;
export type UserId   = Brand<string, 'UserId'>;
export type OrderId  = Brand<string, 'OrderId'>;
export type RefundId = Brand<string, 'RefundId'>;

/**
 * An amount in the smallest unit of some currency. Deliberately NOT called
 * `Cents`: for JPY/KRW the minor unit is the major unit. The currency itself is
 * never carried alongside — it is read from the Order, so there is nothing to
 * disagree with.
 */
export type MinorUnits = Brand<number, 'MinorUnits'>;

export function assertNever(x: never, context: string): never {
  throw new Error(`Unhandled case in ${context}: ${JSON.stringify(x)}`);
}
```

## 4. `src/refunds/contract.ts` — parse, don't validate

```ts
import { z } from 'zod';
import type { MinorUnits, OrderId, TenantId, UserId } from '../domain/branded';

export const REFUND_REASONS = [
  'DUPLICATE',
  'FRAUDULENT',
  'REQUESTED_BY_CUSTOMER',
  'OTHER',
] as const;
export type RefundReason = (typeof REFUND_REASONS)[number];

/**
 * Note the omissions, they are the design:
 *  - no `tenantId` / `userId` in the body. They come from the session only, so a
 *    caller cannot name a tenant that is not theirs.
 *  - no `currency`. Read from the Order; there is no second copy to drift.
 *  - `amountCents` is required. There is no "omit for full refund" shorthand,
 *    because a dropped field would then silently mean "refund everything".
 */
export const RefundRequestBody = z.object({
  orderId: z.string().min(1).max(64),
  amountCents: z.number().int().positive().max(100_000_000),
  reason: z.enum(REFUND_REASONS),
  note: z.string().max(500).optional(),
});

/** Idempotency key is REQUIRED. An optional idempotency key is a suggestion. */
export const IdempotencyKey = z
  .string()
  .min(8, 'Idempotency-Key must be at least 8 characters')
  .max(255)
  .regex(/^[A-Za-z0-9._:-]+$/, 'Idempotency-Key must be URL-safe');

export interface RefundCommand {
  tenantId: TenantId;
  userId: UserId;
  orderId: OrderId;
  amountCents: MinorUnits;
  reason: RefundReason;
  note?: string;
  idempotencyKey: string;
}

export function parseRefundCommand(input: {
  body: unknown;
  idempotencyKey: unknown;
  session: { userId: string; tenantId: string };
}): RefundCommand {
  const body = RefundRequestBody.parse(input.body);
  return {
    tenantId: input.session.tenantId as TenantId,
    userId: input.session.userId as UserId,
    orderId: body.orderId as OrderId,
    amountCents: body.amountCents as MinorUnits,
    reason: body.reason,
    note: body.note,
    idempotencyKey: IdempotencyKey.parse(input.idempotencyKey),
  };
}
```

## 5. `src/refunds/result.ts`

```ts
import type { Refund } from '@prisma/client';

export type RefundFailure =
  | { kind: 'ORDER_NOT_FOUND' }
  | { kind: 'ORDER_NOT_REFUNDABLE'; detail: string }
  | { kind: 'AMOUNT_EXCEEDS_REFUNDABLE'; totalCents: number; alreadyRefundedCents: number }
  | { kind: 'IDEMPOTENCY_KEY_REUSED'; existingRefundId: string }
  | { kind: 'STRIPE_DECLINED'; code: string; message: string }
  | { kind: 'REFUND_INDETERMINATE'; refundId: string };

export type RefundOutcome =
  | { ok: true; replayed: boolean; refund: Refund }
  | { ok: false; failure: RefundFailure };
```

## 6. `src/refunds/pgErrors.ts`

```ts
import { Prisma } from '@prisma/client';

function errorText(e: Prisma.PrismaClientKnownRequestError): string {
  const meta = e.meta as Record<string, unknown> | undefined;
  return `${e.code} ${String(meta?.code ?? '')} ${String(meta?.message ?? '')} ${String(
    meta?.target ?? '',
  )} ${e.message}`;
}

export function isUniqueViolation(e: unknown, constraint: string): boolean {
  if (!(e instanceof Prisma.PrismaClientKnownRequestError)) return false;
  const text = errorText(e);
  return (e.code === 'P2002' || text.includes('23505')) && text.includes(constraint);
}

/**
 * Deliberately narrow: it must match BOTH the SQLSTATE and the constraint name.
 * If it stops matching (a constraint gets renamed), the error propagates as a
 * 500 rather than being mistaken for a clean 422. Fail closed, loudly.
 * `tests/refunds.constraints.test.ts` proves it goes red when it should.
 */
export function isCheckViolation(e: unknown, constraint: string): boolean {
  if (!(e instanceof Prisma.PrismaClientKnownRequestError)) return false;
  const text = errorText(e);
  return text.includes('23514') && text.includes(constraint);
}
```

## 7. `src/refunds/service.ts` — the core

```ts
import type { PrismaClient, Prisma, Refund } from '@prisma/client';
import type Stripe from 'stripe';
import { assertNever } from '../domain/branded';
import type { RefundCommand, RefundReason } from './contract';
import type { RefundOutcome } from './result';
import { isCheckViolation, isUniqueViolation } from './pgErrors';

const ORDER_CEILING = 'Order_refundedCents_within_total';
const IDEMPOTENCY_UNIQUE = 'Refund_tenantId_idempotencyKey_key';

export interface RefundDeps {
  prisma: PrismaClient;
  stripe: Stripe;
  logger: { info(o: object, m: string): void; error(o: object, m: string): void };
}

function toStripeReason(r: RefundReason): Stripe.RefundCreateParams.Reason | undefined {
  switch (r) {
    case 'DUPLICATE':
      return 'duplicate';
    case 'FRAUDULENT':
      return 'fraudulent';
    case 'REQUESTED_BY_CUSTOMER':
      return 'requested_by_customer';
    case 'OTHER':
      // Stripe's enum is closed; free-form context rides in metadata instead.
      return undefined;
    default:
      return assertNever(r, 'toStripeReason');
  }
}

/**
 * Terminal = we KNOW Stripe did not move money, so releasing the reservation is
 * safe. Everything else is indeterminate and the reservation must be held.
 * Getting this classification wrong in the permissive direction is the
 * double-refund bug, so the default is "hold".
 */
function isTerminalStripeError(err: unknown): err is Stripe.errors.StripeError {
  const type = (err as { type?: string })?.type;
  return (
    type === 'StripeInvalidRequestError' ||
    type === 'StripeCardError' ||
    type === 'StripeAuthenticationError' ||
    type === 'StripePermissionError'
  );
}

export async function createRefund(
  deps: RefundDeps,
  cmd: RefundCommand,
): Promise<RefundOutcome> {
  const { prisma, stripe, logger } = deps;

  // ── Phase 1: reserve in Postgres before any money moves ───────────────────
  type Reserved =
    | { kind: 'reserved'; refund: Refund; paymentIntentId: string }
    | { kind: 'not_found' }
    | { kind: 'not_refundable'; detail: string }
    | { kind: 'exceeds'; totalCents: number; alreadyRefundedCents: number };

  let reserved: Reserved;
  try {
    reserved = await prisma.$transaction(
      async (tx): Promise<Reserved> => {
        // Composite lookup. There is no code path that fetches an Order by id alone.
        const order = await tx.order.findUnique({
          where: { id_tenantId: { id: cmd.orderId, tenantId: cmd.tenantId } },
        });
        if (!order) return { kind: 'not_found' };
        if (!order.stripePaymentIntentId) {
          return { kind: 'not_refundable', detail: 'Order has no captured payment to refund' };
        }

        // Insert first: on replay the unique index aborts the whole transaction,
        // so the ledger below is never touched twice.
        const refund = await tx.refund.create({
          data: {
            orderId: cmd.orderId,
            tenantId: cmd.tenantId,
            amountCents: cmd.amountCents,
            reason: cmd.reason,
            note: cmd.note,
            idempotencyKey: cmd.idempotencyKey,
            status: 'PENDING',
          },
        });

        // Single atomic increment. The row lock serializes concurrent partial
        // refunds and the CHECK constraint rejects any that would breach the
        // total — there is no read-then-write window to race.
        try {
          const affected = await tx.$executeRaw`
            UPDATE "Order"
               SET "refundedCents" = "refundedCents" + ${cmd.amountCents}
             WHERE "id" = ${cmd.orderId} AND "tenantId" = ${cmd.tenantId}`;
          if (affected !== 1) throw new Error(`Reserve touched ${affected} rows, expected 1`);
        } catch (e) {
          if (isCheckViolation(e, ORDER_CEILING)) {
            return {
              kind: 'exceeds',
              totalCents: order.totalCents,
              alreadyRefundedCents: order.refundedCents,
            };
          }
          throw e;
        }

        return { kind: 'reserved', refund, paymentIntentId: order.stripePaymentIntentId };
      },
      { isolationLevel: 'ReadCommitted', timeout: 10_000 },
    );
  } catch (e) {
    if (isUniqueViolation(e, IDEMPOTENCY_UNIQUE)) {
      return replay(prisma, cmd);
    }
    throw e;
  }

  switch (reserved.kind) {
    case 'not_found':
      return { ok: false, failure: { kind: 'ORDER_NOT_FOUND' } };
    case 'not_refundable':
      return { ok: false, failure: { kind: 'ORDER_NOT_REFUNDABLE', detail: reserved.detail } };
    case 'exceeds':
      return {
        ok: false,
        failure: {
          kind: 'AMOUNT_EXCEEDS_REFUNDABLE',
          totalCents: reserved.totalCents,
          alreadyRefundedCents: reserved.alreadyRefundedCents,
        },
      };
    case 'reserved':
      break;
    default:
      return assertNever(reserved, 'createRefund reservation');
  }

  const { refund, paymentIntentId } = reserved;

  // ── Phase 2: call Stripe ──────────────────────────────────────────────────
  let stripeRefund: Stripe.Refund;
  try {
    stripeRefund = await stripe.refunds.create(
      {
        payment_intent: paymentIntentId,
        amount: refund.amountCents,
        reason: toStripeReason(cmd.reason),
        metadata: {
          refundId: refund.id,
          orderId: cmd.orderId,
          tenantId: cmd.tenantId,
          requestedByUserId: cmd.userId,
          note: cmd.note ?? '',
        },
      },
      // Derived from our own row id, so a retry of THIS request is a no-op at
      // Stripe even if our process died before recording the response.
      { idempotencyKey: `refund:${refund.id}` },
    );
  } catch (err) {
    if (isTerminalStripeError(err)) {
      const code = (err as Stripe.errors.StripeError).code ?? 'stripe_error';
      await releaseReservation(prisma, refund.id, code);
      return {
        ok: false,
        failure: {
          kind: 'STRIPE_DECLINED',
          code,
          message: (err as Error).message,
        },
      };
    }
    // Indeterminate (timeout, connection reset, 5xx, idempotency conflict): we
    // do NOT know whether money moved. Hold the reservation, stay PENDING, and
    // let the reconciler ask Stripe. Releasing here is the double-refund bug.
    logger.error(
      { refundId: refund.id, orderId: cmd.orderId, err },
      'refund left PENDING: indeterminate Stripe outcome',
    );
    return { ok: false, failure: { kind: 'REFUND_INDETERMINATE', refundId: refund.id } };
  }

  // ── Phase 3: settle ───────────────────────────────────────────────────────
  return settle(prisma, refund.id, stripeRefund);
}

/** Idempotent replay. Same key + different parameters is a conflict, not a hit. */
async function replay(prisma: PrismaClient, cmd: RefundCommand): Promise<RefundOutcome> {
  const existing = await prisma.refund.findUnique({
    where: {
      tenantId_idempotencyKey: {
        tenantId: cmd.tenantId,
        idempotencyKey: cmd.idempotencyKey,
      },
    },
  });
  if (!existing) throw new Error('Idempotency conflict with no matching row; retry the request');

  const sameRequest =
    existing.orderId === cmd.orderId &&
    existing.amountCents === cmd.amountCents &&
    existing.reason === cmd.reason;

  if (!sameRequest) {
    return {
      ok: false,
      failure: { kind: 'IDEMPOTENCY_KEY_REUSED', existingRefundId: existing.id },
    };
  }
  if (existing.status === 'PENDING') {
    return { ok: false, failure: { kind: 'REFUND_INDETERMINATE', refundId: existing.id } };
  }
  if (existing.status === 'FAILED') {
    return {
      ok: false,
      failure: {
        kind: 'STRIPE_DECLINED',
        code: existing.failureCode ?? 'unknown',
        message: 'Refund previously failed',
      },
    };
  }
  return { ok: true, replayed: true, refund: existing };
}

export async function settle(
  prisma: PrismaClient,
  refundId: string,
  stripeRefund: Stripe.Refund,
): Promise<RefundOutcome> {
  switch (stripeRefund.status) {
    case 'succeeded':
    case 'pending':
    case 'requires_action': {
      // Money is committed or in flight: keep the reservation either way.
      const updated = await prisma.refund.update({
        where: { id: refundId },
        data: {
          stripeRefundId: stripeRefund.id,
          status: stripeRefund.status === 'succeeded' ? 'SUCCEEDED' : 'PENDING',
        },
      });
      return stripeRefund.status === 'succeeded'
        ? { ok: true, replayed: false, refund: updated }
        : { ok: false, failure: { kind: 'REFUND_INDETERMINATE', refundId } };
    }
    case 'failed':
    case 'canceled':
    default: {
      const code = stripeRefund.failure_reason ?? stripeRefund.status ?? 'failed';
      await releaseReservation(prisma, refundId, code, stripeRefund.id);
      return {
        ok: false,
        failure: { kind: 'STRIPE_DECLINED', code, message: `Stripe refund ${stripeRefund.status}` },
      };
    }
  }
}

/**
 * Give the reserved amount back to the order's refundable balance.
 * The `count === 0` guard is the device: if anything else already moved this
 * refund out of PENDING (a reconciler, a webhook), we must not decrement again.
 */
export async function releaseReservation(
  prisma: PrismaClient,
  refundId: string,
  failureCode: string,
  stripeRefundId?: string,
): Promise<void> {
  await prisma.$transaction(async (tx) => {
    const { count } = await tx.refund.updateMany({
      where: { id: refundId, status: 'PENDING' },
      data: { status: 'FAILED', failureCode, stripeRefundId },
    });
    if (count === 0) return;

    const r = await tx.refund.findUniqueOrThrow({ where: { id: refundId } });
    const affected = await tx.$executeRaw`
      UPDATE "Order"
         SET "refundedCents" = "refundedCents" - ${r.amountCents}
       WHERE "id" = ${r.orderId} AND "tenantId" = ${r.tenantId}`;
    if (affected !== 1) throw new Error(`Release touched ${affected} rows, expected 1`);
  });
}
```

## 8. `src/refunds/handler.ts` — Express

```ts
import type { Request, Response } from 'express';
import { ZodError } from 'zod';
import { assertNever } from '../domain/branded';
import { parseRefundCommand } from './contract';
import { createRefund, type RefundDeps } from './service';
import type { RefundFailure } from './result';

declare module 'express-serve-static-core' {
  interface Request {
    session?: { userId: string; tenantId: string; can(cap: string): boolean };
  }
}

function statusFor(f: RefundFailure): number {
  switch (f.kind) {
    case 'ORDER_NOT_FOUND':
      return 404;
    case 'ORDER_NOT_REFUNDABLE':
    case 'IDEMPOTENCY_KEY_REUSED':
      return 409;
    case 'AMOUNT_EXCEEDS_REFUNDABLE':
      return 422;
    case 'STRIPE_DECLINED':
      return 402;
    case 'REFUND_INDETERMINATE':
      return 202; // accepted, outcome not yet known — safe to poll, not to retry
    default:
      return assertNever(f, 'statusFor');
  }
}

export function makeRefundHandler(deps: RefundDeps) {
  return async function postRefund(req: Request, res: Response): Promise<void> {
    const session = req.session;
    if (!session) {
      res.status(401).json({ error: { code: 'UNAUTHENTICATED' } });
      return;
    }
    if (!session.can('refunds:create')) {
      res.status(403).json({ error: { code: 'FORBIDDEN' } });
      return;
    }

    let cmd;
    try {
      cmd = parseRefundCommand({
        body: req.body,
        idempotencyKey: req.header('Idempotency-Key'),
        session,
      });
    } catch (e) {
      if (e instanceof ZodError) {
        res.status(400).json({ error: { code: 'INVALID_REQUEST', issues: e.issues } });
        return;
      }
      throw e;
    }

    const outcome = await createRefund(deps, cmd);

    if (outcome.ok) {
      const r = outcome.refund;
      res.status(outcome.replayed ? 200 : 201).json({
        id: r.id,
        orderId: r.orderId,
        amountCents: r.amountCents,
        reason: r.reason,
        note: r.note,
        status: r.status,
        stripeRefundId: r.stripeRefundId,
        createdAt: r.createdAt,
      });
      return;
    }

    const { failure } = outcome;
    res.status(statusFor(failure)).json({
      error: {
        code: failure.kind,
        ...(failure.kind === 'AMOUNT_EXCEEDS_REFUNDABLE' && {
          refundableCents: failure.totalCents - failure.alreadyRefundedCents,
        }),
        ...(failure.kind === 'ORDER_NOT_REFUNDABLE' && { detail: failure.detail }),
        ...(failure.kind === 'STRIPE_DECLINED' && { detail: failure.message }),
        ...(failure.kind === 'REFUND_INDETERMINATE' && {
          refundId: failure.refundId,
          detail: 'Refund submitted; outcome pending. Poll GET /refunds/:id. Do not retry.',
        }),
        ...(failure.kind === 'IDEMPOTENCY_KEY_REUSED' && {
          detail: 'Idempotency-Key already used with different parameters',
          existingRefundId: failure.existingRefundId,
        }),
      },
    });
  };
}
```

Route wiring:

```ts
router.post('/refunds', requireSession, makeRefundHandler({ prisma, stripe, logger }));
```

## 9. `src/refunds/reconcile.ts` — the thing that makes 202 honest

```ts
import type { PrismaClient } from '@prisma/client';
import type Stripe from 'stripe';
import { settle, releaseReservation } from './service';

/** Run every minute. Without this, PENDING rows hold reservations forever. */
export async function reconcilePendingRefunds(
  prisma: PrismaClient,
  stripe: Stripe,
  olderThanMs = 60_000,
): Promise<{ scanned: number; resolved: number }> {
  const cutoff = new Date(Date.now() - olderThanMs);
  const pending = await prisma.refund.findMany({
    where: { status: 'PENDING', createdAt: { lt: cutoff } },
    take: 200,
    orderBy: { createdAt: 'asc' },
  });

  let resolved = 0;
  for (const r of pending) {
    // Our Stripe idempotency key is derived from the row id, so replaying the
    // exact same create returns the original refund if one exists — and creates
    // nothing new if it does not.
    const order = await prisma.order.findUniqueOrThrow({
      where: { id_tenantId: { id: r.orderId, tenantId: r.tenantId } },
    });
    if (!order.stripePaymentIntentId) {
      await releaseReservation(prisma, r.id, 'order_lost_payment_intent');
      resolved++;
      continue;
    }
    const sr = await stripe.refunds.create(
      { payment_intent: order.stripePaymentIntentId, amount: r.amountCents },
      { idempotencyKey: `refund:${r.id}` },
    );
    const out = await settle(prisma, r.id, sr);
    if (out.ok || out.failure.kind !== 'REFUND_INDETERMINATE') resolved++;
  }
  return { scanned: pending.length, resolved };
}
```

## 10. `tests/refunds.constraints.test.ts` — proving the devices go red

```ts
import { describe, expect, it } from 'vitest';
import { prisma } from './helpers/db';
import { isCheckViolation } from '../src/refunds/pgErrors';

describe('database-layer devices', () => {
  it('refuses to over-refund even from raw SQL', async () => {
    const o = await seedOrder({ totalCents: 5_000, refundedCents: 4_000 });
    await expect(
      prisma.$executeRaw`UPDATE "Order" SET "refundedCents" = "refundedCents" + 1001 WHERE id = ${o.id}`,
    ).rejects.toSatisfy((e) => isCheckViolation(e, 'Order_refundedCents_within_total'));
  });

  // near-miss: the constraint must NOT fire one cent below the ceiling
  it('permits a refund that exactly exhausts the order', async () => {
    const o = await seedOrder({ totalCents: 5_000, refundedCents: 4_000 });
    await prisma.$executeRaw`UPDATE "Order" SET "refundedCents" = "refundedCents" + 1000 WHERE id = ${o.id}`;
    const after = await prisma.order.findUniqueOrThrow({ where: { id: o.id } });
    expect(after.refundedCents).toBe(5_000);
  });

  it('refuses a Refund row whose tenantId disagrees with its Order', async () => {
    const o = await seedOrder({ tenantId: 'tenant_a' });
    await expect(
      prisma.refund.create({
        data: {
          orderId: o.id,
          tenantId: 'tenant_b',
          amountCents: 100,
          reason: 'DUPLICATE',
          idempotencyKey: 'k-cross-tenant',
        },
      }),
    ).rejects.toThrow(/foreign key|Refund_orderId_tenantId_fkey/i);
  });

  it('concurrent partial refunds cannot jointly exceed the total', async () => {
    const o = await seedOrder({ totalCents: 1_000 });
    const attempt = () =>
      createRefund(deps, cmd({ orderId: o.id, amountCents: 600, idempotencyKey: rnd() }));
    const [a, b] = await Promise.all([attempt(), attempt()]);
    expect([a.ok, b.ok].filter(Boolean)).toHaveLength(1);
    const after = await prisma.order.findUniqueOrThrow({ where: { id: o.id } });
    expect(after.refundedCents).toBe(600);
  });

  it('an indeterminate Stripe failure does not release the reservation', async () => {
    const o = await seedOrder({ totalCents: 1_000 });
    stripeMock.refunds.create.mockRejectedValueOnce({ type: 'StripeConnectionError' });
    const out = await createRefund(deps, cmd({ orderId: o.id, amountCents: 1_000 }));
    expect(out).toMatchObject({ ok: false, failure: { kind: 'REFUND_INDETERMINATE' } });
    const after = await prisma.order.findUniqueOrThrow({ where: { id: o.id } });
    expect(after.refundedCents).toBe(1_000); // still held
  });
});
```

---

**What I consciously left possible** — the part that matters most:

- **A window where money has moved and the row says `PENDING`.** Unavoidable across two systems; the reconciler closes it in ~60s. What's *not* possible is losing the record entirely.
- **`refundedCents` can drift from `SUM(refunds)`** if a refund is created directly in Stripe's dashboard. Add a Stripe `charge.refunded` webhook and a nightly parity check; I didn't write those since you didn't mention webhooks.
- **`reason` accepted as an open string** would have been closer to your spec. I closed it to an enum because Stripe's `reason` field is closed — free text there is silently dropped. Your original strings survive in `note`.
- **`amountCents` is a misnomer for zero-decimal currencies** (JPY, KRW). I kept your field name and named the branded type `MinorUnits` instead of renaming your API.
- **`session.can('refunds:create')`** is a stub. Tenant isolation is enforced structurally; *who within the tenant* may refund is your capability model, and I don't know its shape.

`★ Insight ─────────────────────────────────────`
The single highest-leverage line in all of this is the `CHECK` constraint in the migration, not anything in TypeScript. Application-level guards protect one code path; a `CHECK` protects every path — this handler, a future admin tool, a migration script, a support engineer in `psql`, and whatever service someone writes in Go next year. That's the "push it down to the data layer" move: the database is the one type system all your services share.
`─────────────────────────────────────────────────`

One decision I'd genuinely rather you make than guess at: **should a `409 IDEMPOTENCY_KEY_REUSED` be per-tenant (as written) or per-order?** Per-tenant matches Stripe and catches a client that reuses a key across different orders — the more dangerous bug. Per-order is more forgiving of clients that key off something like `orderId + attempt`. If you want per-order, change the unique index to `("orderId", "idempotencyKey")` and the lookup in `replay()` to match; everything else stands.