**Handler:**

```typescript
import { Router, Request, Response } from 'express';
import Stripe from 'stripe';
import { prisma } from '@/lib/prisma';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!);

interface AuthenticatedRequest extends Request {
  session: { userId: string; tenantId: string };
}

interface RefundRequest {
  orderId: string;
  amountCents: number;
  reason: string;
}

const router = Router();

router.post('/refunds', async (req: AuthenticatedRequest, res: Response) => {
  const { orderId, amountCents, reason } = req.body as RefundRequest;
  const { tenantId } = req.session;

  if (!orderId || amountCents == null || !reason) {
    return res.status(400).json({ error: 'Missing required fields' });
  }

  if (!Number.isInteger(amountCents) || amountCents <= 0) {
    return res.status(400).json({ error: 'amountCents must be positive' });
  }

  const order = await prisma.order.findUnique({
    where: { id: orderId },
  });

  if (!order) {
    return res.status(404).json({ error: 'Order not found' });
  }

  if (order.tenantId !== tenantId) {
    return res.status(403).json({ error: 'Not authorized' });
  }

  if (amountCents > order.totalCents) {
    return res.status(400).json({ error: 'Refund exceeds order total' });
  }

  if (!order.stripeChargeId) {
    return res.status(400).json({ error: 'Order has no Stripe charge' });
  }

  let stripeRefund;
  try {
    stripeRefund = await stripe.refunds.create({
      charge: order.stripeChargeId,
      amount: amountCents,
      metadata: { orderId, tenantId },
    });
  } catch (error) {
    console.error('Stripe refund failed:', error);
    return res.status(500).json({ error: 'Refund processing failed' });
  }

  const refund = await prisma.refund.create({
    data: {
      orderId,
      amountCents,
      reason,
      stripeRefundId: stripeRefund.id,
      status: stripeRefund.status,
    },
  });

  res.status(201).json(refund);
});

export default router;
```

**Prisma schema additions:**

```prisma
model Order {
  id            String   @id @default(cuid())
  tenantId      String
  totalCents    Int
  currency      String
  stripeChargeId String?  // added for refunds
  createdAt     DateTime @default(now())
  
  refunds       Refund[]
  tenant        Tenant   @relation(fields: [tenantId], references: [id], onDelete: Cascade)
  
  @@index([tenantId])
  @@index([stripeChargeId])
}

model Refund {
  id             String   @id @default(cuid())
  orderId        String
  amountCents    Int
  reason         String
  stripeRefundId String?  @unique // added
  status         String   @default("pending") // added: pending|succeeded|failed
  createdAt      DateTime @default(now())
  
  order          Order    @relation(fields: [orderId], references: [id], onDelete: Cascade)
  
  @@index([orderId])
  @@index([stripeRefundId])
}
```

**Migration:**

```sql
-- migration_name.sql
ALTER TABLE "Refund" ADD COLUMN "stripeRefundId" TEXT UNIQUE;
ALTER TABLE "Refund" ADD COLUMN "status" TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE "Order" ADD COLUMN "stripeChargeId" TEXT;

CREATE INDEX "Refund_stripeRefundId_idx" ON "Refund"("stripeRefundId");
CREATE INDEX "Order_stripeChargeId_idx" ON "Order"("stripeChargeId");
```

★ Insight ─────────────────────────────────────
The handler validates authorization by checking `order.tenantId` against the session's `tenantId` before touching Stripe or the database — a critical check for multi-tenant safety. The `stripeChargeId` field on Order is essential: Stripe's refunds API requires a charge ID, not just an order ID, so we've added it to the schema. The `status` field tracks Stripe refund state (pending/succeeded/failed) so you can reconcile async webhooks later.
─────────────────────────────────────────────