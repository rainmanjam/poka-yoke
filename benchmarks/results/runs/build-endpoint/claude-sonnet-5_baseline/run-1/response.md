Using `poka-yoke:design` to shape this — refunds are the textbook case for "what happens on the second call," so I ran the misuse checklist before writing the signature: swappable params (orderId/reason are both strings), forgettable steps (tenant scoping, idempotency), illegal states (a Refund row that exists but nothing happened at Stripe), and the retry/crash case (partial network failure between insert and Stripe call). The design below closes each at the highest rung it'll take.

**Key decisions, stated so they don't get silently undone later:**
- **Idempotency-Key is a required header**, not derived from `{orderId, amountCents, reason}` — two legitimate identical partial refunds must both succeed, so content-based dedup would be wrong. The key is enforced by a DB `UNIQUE` constraint (rung 1: constraint), not a check-then-insert race.
- **Order is locked with `SELECT ... FOR UPDATE`** inside the same transaction as the overcommit check, so two concurrent refund requests against one order can't both read "$0 already refunded" and both pass.
- **Refund starts `PENDING` and is persisted before Stripe is called.** If the process dies between the DB write and the Stripe call, the retry (same Idempotency-Key) finds the `PENDING` row via the unique-constraint catch and resumes instead of creating a second row or silently doing nothing.
- **`reason` is a closed enum**, not a free string, so a new refund reason next year is a compile break at every switch, not a silent no-op branch.
- Left possible, on purpose: no RBAC check beyond "authenticated member of the tenant" — the spec didn't say refunds need elevated permissions, and adding a role check invents a requirement. Flagging it rather than guessing.

```prisma
// schema.prisma — additions only; existing Order/Refund columns unchanged

enum RefundStatus {
  PENDING
  SUCCEEDED
  FAILED
}

enum RefundReason {
  REQUESTED_BY_CUSTOMER
  DUPLICATE
  FRAUDULENT
  OTHER
}

model Order {
  id                    String   @id @default(cuid())
  tenantId              String
  totalCents            Int
  currency              String
  // Added: refunds are issued against the PaymentIntent from checkout.
  // Assumption: this is captured at order-creation time elsewhere; if it
  // isn't yet, that's a prerequisite for this endpoint, not part of it.
  stripePaymentIntentId String

  refunds Refund[]

  @@index([tenantId])
}

model Refund {
  id             String       @id @default(cuid())
  orderId        String
  order          Order        @relation(fields: [orderId], references: [id])
  amountCents    Int
  reason         RefundReason
  status         RefundStatus @default(PENDING)
  idempotencyKey String       @unique
  stripeRefundId String?      @unique
  failureReason  String?
  createdAt      DateTime     @default(now())
  updatedAt      DateTime     @updatedAt

  @@index([orderId])
}
```

```sql
-- migrations/20260822000000_add_refund_workflow/migration.sql

CREATE TYPE "RefundStatus" AS ENUM ('PENDING', 'SUCCEEDED', 'FAILED');
CREATE TYPE "RefundReason" AS ENUM ('REQUESTED_BY_CUSTOMER', 'DUPLICATE', 'FRAUDULENT', 'OTHER');

ALTER TABLE "Order"
  ADD COLUMN "stripePaymentIntentId" TEXT NOT NULL DEFAULT '';
ALTER TABLE "Order"
  ALTER COLUMN "stripePaymentIntentId" DROP DEFAULT;
-- The DEFAULT ''/DROP DEFAULT two-step lets this ship as a backfillable
-- migration against existing rows without a manual data pass blocking deploy.
-- Replace '' with real PaymentIntent ids before relying on refunds in prod.

ALTER TABLE "Refund"
  ADD COLUMN "status" "RefundStatus" NOT NULL DEFAULT 'PENDING',
  ADD COLUMN "reason_new" "RefundReason",
  ADD COLUMN "idempotencyKey" TEXT,
  ADD COLUMN "stripeRefundId" TEXT,
  ADD COLUMN "failureReason" TEXT,
  ADD COLUMN "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT now();

-- reason was a free-form column before; this repo has no data yet per the
-- brief, so we drop/rename rather than write a backfill mapping. In a real
-- migration with existing rows, map old values into the enum first.
ALTER TABLE "Refund" DROP COLUMN "reason";
ALTER TABLE "Refund" RENAME COLUMN "reason_new" TO "reason";
ALTER TABLE "Refund" ALTER COLUMN "reason" SET NOT NULL;
ALTER TABLE "Refund" ALTER COLUMN "idempotencyKey" SET NOT NULL;

CREATE UNIQUE INDEX "Refund_idempotencyKey_key" ON "Refund"("idempotencyKey");
CREATE UNIQUE INDEX "Refund_stripeRefundId_key" ON "Refund"("stripeRefundId");
CREATE INDEX "Refund_orderId_idx" ON "Refund"("orderId");

-- Data-layer device: this holds even for a script that bypasses the app.
ALTER TABLE "Refund" ADD CONSTRAINT "Refund_amountCents_positive"
  CHECK ("amountCents" > 0);
```

```typescript
// types/refund.ts
import { z } from 'zod';

// Branded IDs: OrderId and TenantId are both strings but must never be
// passed to each other's parameter slot.
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type OrderId = Brand<string, 'OrderId'>;
export type TenantId = Brand<string, 'TenantId'>;
export type UserId = Brand<string, 'UserId'>;

export const RefundReasonSchema = z.enum([
  'REQUESTED_BY_CUSTOMER',
  'DUPLICATE',
  'FRAUDULENT',
  'OTHER',
]);
export type RefundReason = z.infer<typeof RefundReasonSchema>;

// Parse-don't-validate: this is the only place a raw request body is
// touched. Everything past this point works with RefundRequest, never
// with unparsed JSON.
export const RefundRequestSchema = z.object({
  orderId: z.string().min(1),
  amountCents: z.number().int().positive(),
  reason: RefundReasonSchema,
});
export type RefundRequest = z.infer<typeof RefundRequestSchema>;

// Only the three reasons Stripe's API accepts map through; everything
// else rides in metadata instead of silently becoming "requested_by_customer".
export function toStripeReason(
  reason: RefundReason
): 'duplicate' | 'fraudulent' | 'requested_by_customer' | undefined {
  switch (reason) {
    case 'DUPLICATE':
      return 'duplicate';
    case 'FRAUDULENT':
      return 'fraudulent';
    case 'REQUESTED_BY_CUSTOMER':
      return 'requested_by_customer';
    case 'OTHER':
      return undefined;
    default: {
      const _exhaustive: never = reason;
      throw new Error(`unhandled RefundReason: ${_exhaustive}`);
    }
  }
}
```

```typescript
// routes/refunds.ts
import type { Request, Response } from 'express';
import { Prisma, PrismaClient, RefundStatus } from '@prisma/client';
import Stripe from 'stripe';
import { RefundRequestSchema, toStripeReason, type OrderId, type TenantId } from '../types/refund';

const prisma = new PrismaClient();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, { apiVersion: '2024-06-20' });

// Session shape is attached by upstream auth middleware; not re-derived here.
interface AuthedRequest extends Request {
  session: { userId: string; tenantId: string };
}

class HttpError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

interface OrderRow {
  id: string;
  tenantId: string;
  totalCents: number;
  currency: string;
  stripePaymentIntentId: string;
}

function isUniqueConstraintOn(e: unknown, field: string): boolean {
  return (
    e instanceof Prisma.PrismaClientKnownRequestError &&
    e.code === 'P2002' &&
    Array.isArray(e.meta?.target) &&
    (e.meta!.target as string[]).includes(field)
  );
}

export async function createRefund(req: AuthedRequest, res: Response): Promise<void> {
  const idempotencyKey = req.header('Idempotency-Key');
  if (!idempotencyKey) {
    throw new HttpError(400, 'Idempotency-Key header is required for refund requests');
  }

  const parsed = RefundRequestSchema.safeParse(req.body);
  if (!parsed.success) {
    throw new HttpError(400, parsed.error.message);
  }
  const { orderId, amountCents, reason } = parsed.data;
  const tenantId = req.session.tenantId as TenantId;

  // Reserve the idempotency key and the refund budget atomically, before
  // Stripe is ever called. Order row is locked so a concurrent refund
  // request for the same order can't read a stale "amount already refunded".
  const refund = await prisma.$transaction(async (tx) => {
    const orders = await tx.$queryRaw<OrderRow[]>`
      SELECT * FROM "Order" WHERE id = ${orderId} AND "tenantId" = ${tenantId} FOR UPDATE
    `;
    const order = orders[0];
    if (!order) {
      throw new HttpError(404, `no order ${orderId} for this tenant`);
    }

    const committed = await tx.refund.aggregate({
      where: { orderId, status: { in: ['PENDING', 'SUCCEEDED'] } },
      _sum: { amountCents: true },
    });
    const alreadyCommitted = committed._sum.amountCents ?? 0;
    if (amountCents > order.totalCents - alreadyCommitted) {
      throw new HttpError(
        422,
        `refund of ${amountCents} exceeds refundable balance (${order.totalCents - alreadyCommitted})`
      );
    }

    try {
      const created = await tx.refund.create({
        data: { orderId, amountCents, reason, idempotencyKey, status: RefundStatus.PENDING },
      });
      return { refund: created, order };
    } catch (e) {
      if (isUniqueConstraintOn(e, 'idempotencyKey')) {
        // Same Idempotency-Key seen before: this is a retry, not a new
        // refund. Reuse whatever that first attempt produced.
        const existing = await tx.refund.findUniqueOrThrow({ where: { idempotencyKey } });
        return { refund: existing, order };
      }
      throw e;
    }
  });

  if (refund.refund.status !== RefundStatus.PENDING) {
    // Replay of an already-resolved request — do not call Stripe again.
    res.status(200).json(refund.refund);
    return;
  }

  try {
    const stripeRefund = await stripe.refunds.create(
      {
        payment_intent: refund.order.stripePaymentIntentId,
        amount: amountCents,
        reason: toStripeReason(reason),
        metadata: { orderId, tenantId, refundId: refund.refund.id, reason },
      },
      { idempotencyKey }
    );

    const updated = await prisma.refund.update({
      where: { id: refund.refund.id },
      data: { status: RefundStatus.SUCCEEDED, stripeRefundId: stripeRefund.id },
    });
    res.status(201).json(updated);
  } catch (err) {
    const failureReason = err instanceof Error ? err.message : 'unknown Stripe error';
    await prisma.refund.update({
      where: { id: refund.refund.id },
      data: { status: RefundStatus.FAILED, failureReason },
    });
    throw new HttpError(502, `Stripe refund failed: ${failureReason}`);
  }
}
```

★ Insight ─────────────────────────────────────
- The `SELECT ... FOR UPDATE` inside `$transaction` is doing more work than the idempotency key: the unique constraint prevents *replaying the same request*, but only a row lock prevents *two different concurrent requests* from each seeing "$0 refunded so far" and both approving a refund that together exceed the order total. They're solving different races.
- Persisting `PENDING` before calling Stripe, then reconciling to `SUCCEEDED`/`FAILED` after, is the standard shape for any handler that calls an external side-effecting API inside an HTTP request — it makes "the process died mid-call" a resumable state instead of an unknown one.
─────────────────────────────────────────────────

One more assumption worth surfacing explicitly rather than guessing silently: `Order` didn't have a Stripe reference before, so I added `stripePaymentIntentId`. If your checkout flow stores something else (a Charge ID, a different PaymentIntent per partial capture), that column name is the thing to change — the rest of the design doesn't depend on which Stripe object it points to.