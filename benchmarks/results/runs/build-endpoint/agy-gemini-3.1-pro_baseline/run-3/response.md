Here is the complete implementation based on your requirements. 

I've made a few reasonable assumptions to tie everything together:
1. **Stripe Integration**: Stripe requires a `payment_intent` or `charge` ID to process a refund. I've assumed the `Order.id` doubles as the Stripe PaymentIntent ID. If they differ, you would just swap `order.id` for `order.stripePaymentIntentId` in the Stripe call.
2. **Framework**: I assumed a standard Express.js/Next.js-style request handler signature.
3. **Data Types**: I assumed IDs are Strings (UUIDs or Stripe IDs) and the reason is optional.

### 1. Prisma Schema (`schema.prisma`)
```prisma
model Order {
  id         String   @id // Assumed to be the Stripe PaymentIntent ID
  tenantId   String
  totalCents Int
  currency   String
  
  // Relation
  refunds    Refund[]
}

model Refund {
  id          String   @id @default(uuid())
  orderId     String
  amountCents Int
  reason      String?
  createdAt   DateTime @default(now())

  // Relation
  order       Order    @relation(fields: [orderId], references: [id], onDelete: Restrict)
}
```

### 2. SQL Migration (`migration.sql`)
```sql
-- CreateTable
CREATE TABLE "Order" (
    "id" TEXT NOT NULL,
    "tenantId" TEXT NOT NULL,
    "totalCents" INTEGER NOT NULL,
    "currency" TEXT NOT NULL,

    CONSTRAINT "Order_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Refund" (
    "id" TEXT NOT NULL,
    "orderId" TEXT NOT NULL,
    "amountCents" INTEGER NOT NULL,
    "reason" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "Refund_pkey" PRIMARY KEY ("id")
);

-- AddForeignKey
ALTER TABLE "Refund" ADD CONSTRAINT "Refund_orderId_fkey" FOREIGN KEY ("orderId") REFERENCES "Order"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
```

### 3. API Handler (`refunds.ts`)
```typescript
import { Request, Response } from 'express';
import { PrismaClient } from '@prisma/client';
import Stripe from 'stripe';

const prisma = new PrismaClient();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY as string, {
  apiVersion: '2024-06-20', // Use your current Stripe API version
});

// Assuming session is attached by prior authentication/authorization middleware
interface AuthenticatedRequest extends Request {
  session: {
    userId: string;
    tenantId: string;
  };
}

export async function createRefundHandler(req: AuthenticatedRequest, res: Response) {
  const { orderId, amountCents, reason } = req.body;
  const { tenantId, userId } = req.session;

  // Basic validation
  if (!orderId || typeof amountCents !== 'number' || amountCents <= 0) {
    return res.status(400).json({ error: 'Valid orderId and amountCents are required' });
  }

  try {
    // 1. Fetch order & verify tenant ownership
    const order = await prisma.order.findUnique({
      where: { id: orderId }
    });

    if (!order) {
      return res.status(404).json({ error: 'Order not found' });
    }

    if (order.tenantId !== tenantId) {
      return res.status(403).json({ error: 'Forbidden: Order belongs to a different tenant' });
    }

    if (amountCents > order.totalCents) {
      return res.status(400).json({ error: 'Refund amount cannot exceed order total' });
    }

    // 2. Execute refund in Stripe
    // Note: 'reason' must be one of: 'duplicate', 'fraudulent', or 'requested_by_customer'
    const stripeRefund = await stripe.refunds.create({
      payment_intent: order.id, 
      amount: amountCents,
      reason: (reason as Stripe.RefundCreateParams.Reason) || undefined,
      metadata: {
        tenantId,
        userId,
      }
    });

    // 3. Persist Refund record in Postgres
    const refund = await prisma.refund.create({
      data: {
        orderId: order.id,
        amountCents,
        reason,
      },
    });

    // 4. Return the successfully created refund
    return res.status(200).json({ 
      refund, 
      stripeRefundId: stripeRefund.id 
    });

  } catch (error: any) {
    console.error('[Refund Error]:', error);
    
    // Catch specific Stripe errors for better client feedback
    if (error instanceof Stripe.errors.StripeError) {
      return res.status(400).json({ error: error.message });
    }

    return res.status(500).json({ error: 'Internal Server Error' });
  }
}
```
{"answer":"I have provided the complete inline code as requested for the Prisma schema, SQL migration, and TypeScript API handler. The code makes the necessary assumptions and meets all your constraints (including writing no files). Let me know if you need any adjustments or if you'd like to implement this in a specific framework!","toolAction":"Finishing task","toolSummary":"Finish task"}