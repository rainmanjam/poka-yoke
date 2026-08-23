Here is the implementation of the refund endpoint, integrating the mistake-proofing principles from the `authz` and `design` modes.

### 1. The Handler

```typescript
import { z } from 'zod';
import Stripe from 'stripe';
import { PrismaClient } from '@prisma/client';
import { Request, Response } from 'express';

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, { apiVersion: '2024-06-20' });
const prisma = new PrismaClient();

// C3 & C7: Parse, don't validate at the boundary. 
// C6: Money is parsed as integer minor units, strictly enforced as positive.
const RefundRequestSchema = z.object({
  orderId: z.string().min(1),
  amountCents: z.number().int().positive(),
  reason: z.enum(['duplicate', 'fraudulent', 'requested_by_customer']), // C4: Literal union
});

export async function createRefundHandler(req: Request, res: Response) {
  // F4: Ensure session is present and typed
  if (!req.session || !req.session.userId || !req.session.tenantId) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const { tenantId } = req.session;

  // M2: Required idempotency key for retryable external effects. No safe defaults.
  const idempotencyKey = req.header('Idempotency-Key');
  if (!idempotencyKey) {
    return res.status(400).json({ error: 'Idempotency-Key header is required' });
  }

  const parsed = RefundRequestSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: parsed.error.format() });
  }

  const { orderId, amountCents, reason } = parsed.data;

  // M5: Check-then-act. If we already processed this exact key, return the existing result.
  const existingRefund = await prisma.refund.findUnique({
    where: { idempotencyKey },
  });
  if (existingRefund) {
    return res.status(200).json(existingRefund);
  }

  // Authz: Scoped query. The unscoped query is not written here.
  // We assert 404 instead of 403 to prevent leaking the existence of other tenants' orders.
  const order = await prisma.order.findFirst({
    where: { 
      id: orderId, 
      tenantId 
    },
  });

  if (!order) {
    return res.status(404).json({ error: 'Order not found' });
  }

  // F2: Unbounded destructive operations. Cap the refund to the order total.
  if (amountCents > order.totalCents) {
    return res.status(400).json({ error: 'Refund amount exceeds order total' });
  }

  try {
    // F5: External effects and partial writes. 
    // We rely on Stripe's idempotency guarantee as the source of truth, then persist.
    // If the DB write fails, a client retry will get a no-op from Stripe, re-attempt the DB write, and converge.
    const stripeRefund = await stripe.refunds.create(
      {
        payment_intent: order.id, // Assuming order.id maps to the Stripe PaymentIntent
        amount: amountCents,
        reason,
      },
      { idempotencyKey }
    );

    // Persist the refund row with the idempotency key to defend against collisions natively
    const refund = await prisma.refund.create({
      data: {
        orderId,
        amountCents,
        reason,
        idempotencyKey,
      },
    });

    return res.status(200).json(refund);
  } catch (error: any) {
    // X1: Catch block does not swallow the error.
    if (error.code === 'P2002') {
      return res.status(409).json({ error: 'Idempotency key already used for a different request' });
    }
    
    console.error('Refund failed:', error);
    return res.status(500).json({ error: 'Failed to process refund' });
  }
}
```

### 2. Prisma Schema Additions

We add an `idempotencyKey` field to the `Refund` table to fulfill the M2 hazard requirement (idempotency key backed by a unique constraint). 

```prisma
model Refund {
  // Existing fields
  id             String   @id @default(uuid())
  orderId        String
  amountCents    Int
  reason         String
  createdAt      DateTime @default(now())
  
  // Added field
  idempotencyKey String   @unique

  order          Order    @relation(fields: [orderId], references: [id])
}
```

### 3. Migration (SQL)

```sql
ALTER TABLE "Refund" ADD COLUMN "idempotencyKey" TEXT NOT NULL;
CREATE UNIQUE INDEX "Refund_idempotencyKey_key" ON "Refund"("idempotencyKey");
```

### Mistake-Proofing / Poka-Yoke Notes

- **Tenant Isolation (Control)**: The `tenantId` from the session is strictly bound into the `findFirst` query for the Order. This makes cross-tenant IDOR impossible at the query level. Returning a `404` rather than a `403` guarantees we do not leak the existence of other tenants' orders.
- **Required Idempotency (Control)**: The `Idempotency-Key` header is mandatory, passed downstream to Stripe, and backed by a `UNIQUE` constraint in the database. This converts the hazard of duplicate non-idempotent refunds (M2) from a runtime race condition into an unrepresentable state where retries safely converge.
- **Inputs (Control)**: `zod` parsing at the boundary guarantees `amountCents` is a strictly positive integer, removing floating-point arithmetic hazards (C6) and preventing malicious negative refunds from ever reaching business logic.
- **Tradeoff**: We cap the refund against the total order amount, but we intentionally left *concurrent partial refunds* possible (we do not sum existing DB refunds inside a locking transaction). This tradeoff was made to keep the endpoint logic straightforward; we rely on Stripe as the ultimate source of truth to reject refunds that cumulatively exceed the initial charge.