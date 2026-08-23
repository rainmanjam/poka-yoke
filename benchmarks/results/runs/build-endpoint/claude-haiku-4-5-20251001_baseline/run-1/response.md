I'll build a complete refund endpoint with schema, migration, and handler. I'm assuming Express.js, that Stripe is initialized as `stripe` client, and session middleware provides auth context.

## 1. Prisma Schema Updates

```typescript
// prisma/schema.prisma (additions/changes)

model Order {
  id                    String      @id @default(cuid())
  tenantId              String
  totalCents            Int
  currency              String
  stripePaymentIntentId String?     // Required to refund
  createdAt             DateTime    @default(now())
  updatedAt             DateTime    @updatedAt
  
  refunds               Refund[]
  
  @@index([tenantId])
  @@index([stripePaymentIntentId])
}

model Refund {
  id              String      @id @default(cuid())
  orderId         String
  order           Order       @relation(fields: [orderId], references: [id], onDelete: Cascade)
  amountCents     Int
  reason          String
  stripeRefundId  String?     // Stripe refund ID after successful call
  status          RefundStatus @default(PENDING)
  errorMessage    String?
  createdAt       DateTime    @default(now())
  updatedAt       DateTime    @updatedAt
  
  @@index([orderId])
  @@index([stripeRefundId])
}

enum RefundStatus {
  PENDING
  SUCCEEDED
  FAILED
}
```

## 2. Migration

```sql
-- prisma/migrations/[timestamp]_add_refund_support/migration.sql

-- Add stripePaymentIntentId to orders
ALTER TABLE "Order" ADD COLUMN "stripePaymentIntentId" TEXT;
CREATE INDEX "Order_stripePaymentIntentId_idx" ON "Order"("stripePaymentIntentId");

-- Create refunds table
CREATE TABLE "Refund" (
  "id" TEXT NOT NULL PRIMARY KEY,
  "orderId" TEXT NOT NULL,
  "amountCents" INTEGER NOT NULL,
  "reason" TEXT NOT NULL,
  "stripeRefundId" TEXT,
  "status" TEXT NOT NULL DEFAULT 'PENDING',
  "errorMessage" TEXT,
  "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "updatedAt" TIMESTAMP(3) NOT NULL,
  CONSTRAINT "Refund_orderId_fkey" FOREIGN KEY ("orderId") REFERENCES "Order" ("id") ON DELETE CASCADE
);

CREATE INDEX "Refund_orderId_idx" ON "Refund"("orderId");
CREATE INDEX "Refund_stripeRefundId_idx" ON "Refund"("stripeRefundId");
```

## 3. Handler

```typescript
// handlers/refunds.ts

import { Request, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import Stripe from 'stripe';

const prisma = new PrismaClient();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

interface AuthenticatedRequest extends Request {
  session: {
    userId: string;
    tenantId: string;
  };
}

export async function createRefund(req: AuthenticatedRequest, res: Response) {
  const { orderId, amountCents, reason } = req.body;
  const { tenantId } = req.session;

  // Validate input
  if (!orderId || !amountCents || !reason) {
    return res.status(400).json({ error: 'Missing required fields' });
  }

  if (amountCents <= 0) {
    return res.status(400).json({ error: 'Amount must be positive' });
  }

  try {
    // Verify order exists and belongs to tenant
    const order = await prisma.order.findUnique({
      where: { id: orderId },
    });

    if (!order) {
      return res.status(404).json({ error: 'Order not found' });
    }

    if (order.tenantId !== tenantId) {
      return res.status(403).json({ error: 'Unauthorized' });
    }

    if (!order.stripePaymentIntentId) {
      return res.status(400).json({ error: 'Order has no associated Stripe payment' });
    }

    // Validate refund amount doesn't exceed order total
    if (amountCents > order.totalCents) {
      return res.status(400).json({ error: 'Refund amount exceeds order total' });
    }

    // Create refund record first (status: PENDING)
    const refund = await prisma.refund.create({
      data: {
        orderId,
        amountCents,
        reason,
        status: 'PENDING',
      },
    });

    // Call Stripe
    let stripeRefundId: string | undefined;
    let errorMessage: string | undefined;

    try {
      const stripeRefund = await stripe.refunds.create({
        payment_intent: order.stripePaymentIntentId,
        amount: amountCents,
        reason: mapRefundReason(reason),
        metadata: {
          refundId: refund.id,
          orderId,
          tenantId,
        },
      });

      stripeRefundId = stripeRefund.id;
    } catch (stripeError) {
      errorMessage =
        stripeError instanceof Stripe.errors.StripeError
          ? stripeError.message
          : 'Unknown Stripe error';
    }

    // Update refund with Stripe result
    const updatedRefund = await prisma.refund.update({
      where: { id: refund.id },
      data: {
        stripeRefundId: stripeRefundId || null,
        status: stripeRefundId ? 'SUCCEEDED' : 'FAILED',
        errorMessage,
        updatedAt: new Date(),
      },
    });

    // Return appropriate status
    if (!stripeRefundId) {
      return res.status(402).json({
        error: 'Refund failed',
        details: errorMessage,
        refund: updatedRefund,
      });
    }

    res.status(201).json(updatedRefund);
  } catch (error) {
    console.error('Refund endpoint error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
}

function mapRefundReason(reason: string): 'duplicate' | 'fraudulent' | 'requested_by_customer' {
  const normalized = reason.toLowerCase();
  if (normalized.includes('duplicate')) return 'duplicate';
  if (normalized.includes('fraud')) return 'fraudulent';
  return 'requested_by_customer';
}
```

## 4. Route Setup

```typescript
// routes/refunds.ts

import { Router } from 'express';
import { createRefund } from '../handlers/refunds';
import { authenticateSession } from '../middleware/auth'; // Your auth middleware

const router = Router();

router.post('/', authenticateSession, createRefund);

export default router;
```

**Key design choices:**
- **Optimistic status**: Refund row created first with PENDING status, then updated after Stripe call. If Stripe fails, you have a record for retry logic.
- **Tenant isolation**: Validates order belongs to tenant before processing.
- **Amount validation**: Prevents over-refunding.
- **Reason mapping**: Maps free-form reason to Stripe's enum.
- **Stripe metadata**: Tracks the refundId in Stripe for reconciliation.
- **Error handling**: Returns 402 (payment required) on Stripe failure, not 5xx, so clients know it's a payment issue.