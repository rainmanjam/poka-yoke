Looking at your request, I'll design a refund endpoint with proper mistake-proofing. This will handle tenant isolation, amount validation, idempotency, and Stripe synchronization.

## Prisma Schema Updates

```prisma
model Refund {
  id              String   @id @default(cuid())
  orderId         String
  order           Order    @relation(fields: [orderId], references: [id], onDelete: Cascade)
  tenantId        String   // Denormalized for tenant filtering
  amountCents     Int      // Must be <= order.totalCents
  reason          String
  status          RefundStatus @default(PENDING)
  stripeRefundId  String?  @unique // Prevents duplicate Stripe refunds
  createdAt       DateTime @default(now())
  updatedAt       DateTime @updatedAt

  @@index([orderId])
  @@index([tenantId])
  @@index([stripeRefundId])
  @@unique([orderId, id]) // Composite for tenant + order safety
}

enum RefundStatus {
  PENDING
  SUCCEEDED
  FAILED
}

// Add to Order model
model Order {
  // ... existing fields
  refunds         Refund[]
}
```

## Migration (SQL)

```sql
-- Create refund status enum
CREATE TYPE "RefundStatus" AS ENUM ('PENDING', 'SUCCEEDED', 'FAILED');

-- Alter Refund table
ALTER TABLE "Refund"
ADD COLUMN "tenantId" TEXT NOT NULL DEFAULT '',
ADD COLUMN "status" "RefundStatus" NOT NULL DEFAULT 'PENDING',
ADD COLUMN "stripeRefundId" TEXT,
ADD COLUMN "updatedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- Create unique constraint on stripeRefundId
CREATE UNIQUE INDEX "Refund_stripeRefundId_key" ON "Refund"("stripeRefundId");

-- Create indexes for tenant filtering and lookups
CREATE INDEX "Refund_orderId_idx" ON "Refund"("orderId");
CREATE INDEX "Refund_tenantId_idx" ON "Refund"("tenantId");
CREATE INDEX "Refund_stripeRefundId_idx" ON "Refund"("stripeRefundId");

-- Backfill tenantId from Order relationship
UPDATE "Refund"
SET "tenantId" = (SELECT "tenantId" FROM "Order" WHERE "Order"."id" = "Refund"."orderId");

-- Make tenantId NOT NULL after backfill
ALTER TABLE "Refund" ALTER COLUMN "tenantId" SET NOT NULL;
```

## Handler Code

```typescript
import Stripe from 'stripe';
import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

interface AuthContext {
  userId: string;
  tenantId: string;
}

interface RefundRequest {
  orderId: string;
  amountCents: number;
  reason: string;
}

interface RefundResponse {
  id: string;
  orderId: string;
  amountCents: number;
  reason: string;
  status: 'PENDING' | 'SUCCEEDED' | 'FAILED';
  stripeRefundId: string | null;
  createdAt: string;
}

export async function handlePostRefunds(
  req: RefundRequest,
  auth: AuthContext
): Promise<RefundResponse> {
  const { orderId, amountCents, reason } = req;
  const { tenantId } = auth;

  // Validate input
  if (amountCents <= 0) {
    throw new Error('Refund amount must be positive');
  }

  if (!reason?.trim()) {
    throw new Error('Refund reason is required');
  }

  // Fetch order and verify tenant ownership (source inspection)
  const order = await prisma.order.findUnique({
    where: { id: orderId },
  });

  if (!order) {
    throw new Error('Order not found');
  }

  if (order.tenantId !== tenantId) {
    throw new Error('Unauthorized: Order does not belong to this tenant');
  }

  // Check refund amount does not exceed order total
  const totalRefunded = await prisma.refund.aggregate({
    where: {
      orderId,
      status: { in: ['SUCCEEDED', 'PENDING'] },
    },
    _sum: {
      amountCents: true,
    },
  });

  const alreadyRefunded = totalRefunded._sum.amountCents || 0;
  if (alreadyRefunded + amountCents > order.totalCents) {
    throw new Error(
      `Refund amount exceeds available balance. Already refunded: ${alreadyRefunded}, ` +
        `requesting: ${amountCents}, total available: ${order.totalCents}`
    );
  }

  // Create idempotency key from orderId + amount + reason hash
  // (in production, could accept from client with signature validation)
  const crypto = await import('crypto');
  const idempotencyKey = crypto
    .createHash('sha256')
    .update(`${orderId}-${amountCents}-${reason}-v1`)
    .digest('hex');

  // Check for existing refund with this idempotency key pattern
  // (using reason + amount + order as natural idempotency key)
  const existingRefund = await prisma.refund.findFirst({
    where: {
      orderId,
      amountCents,
      reason,
      createdAt: {
        gte: new Date(Date.now() - 24 * 60 * 60 * 1000), // within 24h
      },
    },
  });

  if (existingRefund) {
    // Already processed - return existing refund
    return formatRefund(existingRefund);
  }

  // Create refund record in PENDING state
  const refund = await prisma.refund.create({
    data: {
      orderId,
      tenantId,
      amountCents,
      reason,
      status: 'PENDING',
    },
  });

  try {
    // Call Stripe with idempotency key
    const stripeRefund = await stripe.refunds.create(
      {
        // Stripe refund requires charge ID or payment intent ID
        // Assuming you store stripeChargeId on Order
        charge: order.stripeChargeId, // You'll need to add this field to Order
        amount: amountCents,
        reason: mapRefundReason(reason),
        metadata: {
          refundId: refund.id,
          tenantId,
        },
      },
      {
        idempotencyKey: `refund-${refund.id}`,
      }
    );

    // Update refund with Stripe details
    const updatedRefund = await prisma.refund.update({
      where: { id: refund.id },
      data: {
        stripeRefundId: stripeRefund.id,
        status: stripeRefund.status === 'succeeded' ? 'SUCCEEDED' : 'FAILED',
      },
    });

    return formatRefund(updatedRefund);
  } catch (error) {
    // Mark refund as failed but keep the record for audit trail
    await prisma.refund.update({
      where: { id: refund.id },
      data: { status: 'FAILED' },
    });

    throw new Error(`Stripe refund failed: ${(error as Error).message}`);
  }
}

function mapRefundReason(
  reason: string
): 'duplicate' | 'fraudulent' | 'requested_by_customer' {
  const normalized = reason.toLowerCase();
  if (normalized.includes('duplicate')) return 'duplicate';
  if (normalized.includes('fraud')) return 'fraudulent';
  return 'requested_by_customer';
}

function formatRefund(refund: {
  id: string;
  orderId: string;
  amountCents: number;
  reason: string;
  status: string;
  stripeRefundId: string | null;
  createdAt: Date;
}): RefundResponse {
  return {
    id: refund.id,
    orderId: refund.orderId,
    amountCents: refund.amountCents,
    reason: refund.reason,
    status: refund.status as 'PENDING' | 'SUCCEEDED' | 'FAILED',
    stripeRefundId: refund.stripeRefundId,
    createdAt: refund.createdAt.toISOString(),
  };
}
```

**Key design decisions:**

- **Tenant isolation (control)**: Verify orderId belongs to authenticated tenantId before any Stripe call
- **Amount validation (control)**: Check aggregate refunds can't exceed order total via query before Stripe
- **Idempotency (motion-step)**: Use order + amount + reason as natural idempotency key within 24h window; Stripe's `idempotencyKey` header prevents double charges
- **Stripe sync (fixed-value)**: Store `stripeRefundId` with unique constraint—prevents creating duplicate Stripe refunds if API retried
- **Audit trail (detection)**: Keep FAILED refund records for debugging and reconciliation
- **Status tracking**: PENDING→SUCCEEDED/FAILED records full lifecycle

**To use:** Add `stripeChargeId` to your Order model, inject auth context from middleware, and wire the handler to your POST /refunds route.