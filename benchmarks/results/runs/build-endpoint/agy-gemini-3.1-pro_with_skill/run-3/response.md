Based on the `poka-yoke` method and the `design` skill, here is the mistake-proofing reasoning for the requested endpoints and schemas, followed by the complete code.

### Mistake-Proofing Design Reasoning

**Hazards Designed Out (Control Rung):**
1. **Adjacent same-type parameters (C1)**: `orderId` and `tenantId` are both UUIDs. The codebase now uses **branded types** (`OrderId`, `TenantId`) so passing them in the wrong order is a compiler error.
2. **Unvalidated external input (C7)** & **Money as a float (C6)**: We use **parse, don't validate** at the boundary via Zod. Untyped JSON is rejected, and `amountCents` is enforced as a positive integer.
3. **Non-idempotent retries (M2)**: Network retries causing double refunds. An **idempotency key is required** in the payload and the database `UNIQUE(tenantId, idempotencyKey)`, eliminating double-charges (Control).
4. **Tenant-crossing (F6)**: Creating a refund for another tenant's order. The database schema uses a **composite foreign key** `(orderId, tenantId) -> Order(id, tenantId)`. The database physically rejects cross-tenant relations, enforcing isolation regardless of the application query.
5. **Partial Writes (F5)**: Crashing after Stripe succeeds but before the database write, losing the refund entirely. We use **intent-based typestate**, inserting the `Refund` as `PENDING` before the external call, acting as a lock and a recovery record.

**Hazards Consciously Left Possible:**
- **Over-refunding**: We do not `SUM()` existing refunds to check if they exceed the original order total. To reach Control requires complex serializable transactions or DB triggers. We accept Stripe acting as the successive check (Warning) here, as their API rejects refunds exceeding the charge amount.
- **Stuck `PENDING` Records**: A crash mid-Stripe request leaves the database row stuck as `PENDING`. We accept this (Warning/Detection) because it's better to reconcile a known stuck record via a cron job than to lose it completely.

---

### 1. TypeScript Handler

```typescript
import { z } from "zod";
import { PrismaClient } from "@prisma/client";
import Stripe from "stripe";

const prisma = new PrismaClient();
// Assumption: Stripe secret is configured securely in the environment
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY as string, { apiVersion: "2024-04-10" });

// --- POKA-YOKE: C1. Branded Types ---
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type OrderId = Brand<string, "OrderId">;
export type TenantId = Brand<string, "TenantId">;
export type UserId = Brand<string, "UserId">;
export type IdempotencyKey = Brand<string, "IdempotencyKey">;

export type AuthenticatedSession = {
  userId: UserId;
  tenantId: TenantId;
};

// --- POKA-YOKE: C7 & C6. Parse, Don't Validate ---
const RefundRequestSchema = z.object({
  orderId: z.string().uuid().brand<"OrderId">(),
  amountCents: z.number().int().positive(), 
  reason: z.string().min(1).max(255),
  // M2: Required idempotency key, not optional
  idempotencyKey: z.string().min(1).brand<"IdempotencyKey">(),
});

export async function createRefundHandler(req: any, res: any, session: AuthenticatedSession) {
  // 1. Boundary Control: Discard untyped input immediately
  const parsed = RefundRequestSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: parsed.error.format() });
  }
  const data = parsed.data;

  // 2. Locate order and enforce tenant boundaries
  const order = await prisma.order.findUnique({
    where: {
      id_tenantId: { id: data.orderId, tenantId: session.tenantId },
    },
  });

  if (!order || !order.stripeChargeId) {
    return res.status(404).json({ error: "Order not found or missing charge ID" });
  }

  // 3. Motion-step (F5): Record intent BEFORE external effects
  let pendingRefund;
  try {
    pendingRefund = await prisma.refund.create({
      data: {
        orderId: data.orderId,
        tenantId: session.tenantId,
        amountCents: data.amountCents,
        reason: data.reason,
        idempotencyKey: data.idempotencyKey,
        status: "PENDING",
      },
    });
  } catch (error: any) {
    // M5 (Check-then-act guard): Return the existing refund if the idempotency key was reused
    if (error.code === "P2002") {
      const existing = await prisma.refund.findUnique({
        where: {
          tenantId_idempotencyKey: {
            tenantId: session.tenantId,
            idempotencyKey: data.idempotencyKey,
          },
        },
      });
      return res.status(200).json(existing);
    }
    throw error;
  }

  // 4. Execute non-idempotent external call safely
  let stripeRefund;
  try {
    stripeRefund = await stripe.refunds.create(
      {
        charge: order.stripeChargeId,
        amount: data.amountCents,
        reason: "requested_by_customer",
      },
      {
        idempotencyKey: data.idempotencyKey, // M2: Pass the required key
      }
    );
  } catch (stripeError) {
    // X1: Do not swallow the error. Sync the state and re-throw.
    await prisma.refund.update({
      where: { id: pendingRefund.id },
      data: { status: "FAILED" },
    });
    throw stripeError;
  }

  // 5. Finalize state
  const finalizedRefund = await prisma.refund.update({
    where: { id: pendingRefund.id },
    data: { status: "SUCCEEDED" },
  });

  return res.status(200).json(finalizedRefund);
}
```

### 2. Prisma Schema Additions

```prisma
model Order {
  id             String   @id
  tenantId       String
  totalCents     Int
  currency       String
  stripeChargeId String?  // Assumption: Tracked for the payment 

  refunds        Refund[]

  // DEVICE: Composite index enforces F6 Tenant Isolation in DB relationships
  @@unique([id, tenantId])
}

model Refund {
  id             String   @id @default(uuid())
  orderId        String
  amountCents    Int
  reason         String
  createdAt      DateTime @default(now())

  // --- Devices Added ---
  tenantId       String
  idempotencyKey String
  status         String   @default("PENDING")

  // Control (F6): A refund physically cannot be associated with a different tenant's order
  order          Order    @relation(fields: [orderId, tenantId], references: [id, tenantId])

  // Control (M5): Database-level guarantee against concurrent double requests
  @@unique([tenantId, idempotencyKey])
}
```

### 3. SQL Migration

```sql
-- 1. Order Setup: Support for the composite foreign key
CREATE UNIQUE INDEX "Order_id_tenantId_key" ON "Order"("id", "tenantId");

-- 2. Refund Setup: Add new mistake-proofing columns
ALTER TABLE "Refund" ADD COLUMN "tenantId" TEXT NOT NULL;
ALTER TABLE "Refund" ADD COLUMN "idempotencyKey" TEXT NOT NULL;
ALTER TABLE "Refund" ADD COLUMN "status" TEXT NOT NULL DEFAULT 'PENDING';

-- 3. Safety Constraints
-- Enforce idempotency uniquely per tenant
CREATE UNIQUE INDEX "Refund_tenantId_idempotencyKey_key" ON "Refund"("tenantId", "idempotencyKey");

-- Enforce tenant isolation structurally
ALTER TABLE "Refund" ADD CONSTRAINT "Refund_orderId_tenantId_fkey" 
  FOREIGN KEY ("orderId", "tenantId") REFERENCES "Order"("id", "tenantId") ON DELETE RESTRICT ON UPDATE CASCADE;
```
{"answer":"Based on the `poka-yoke` method and the `design` skill, here is the mistake-proofing reasoning for the requested endpoints and schemas, followed by the complete code.\n\n### Mistake-Proofing Design Reasoning\n\n**Hazards Designed Out (Control Rung):**\n1. **Adjacent same-type parameters (C1)**: `orderId` and `tenantId` are both UUIDs. The codebase now uses **branded types** (`OrderId`, `TenantId`) so passing them in the wrong order is a compiler error.\n2. **Unvalidated external input (C7)** \u0026 **Money as a float (C6)**: We use **parse, don't validate** at the boundary via Zod. Untyped JSON is rejected, and `amountCents` is enforced as a positive integer.\n3. **Non-idempotent retries (M2)**: Network retries causing double refunds. An **idempotency key is required** in the payload and the database `UNIQUE(tenantId, idempotencyKey)`, eliminating double-charges (Control).\n4. **Tenant-crossing (F6)**: Creating a refund for another tenant's order. The database schema uses a **composite foreign key** `(orderId, tenantId) -\u003e Order(id, tenantId)`. The database physically rejects cross-tenant relations, enforcing isolation regardless of the application query.\n5. **Partial Writes (F5)**: Crashing after Stripe succeeds but before the database write, losing the refund entirely. We use **intent-based typestate**, inserting the `Refund` as `PENDING` before the external call, acting as a lock and a recovery record.\n\n**Hazards Consciously Left Possible:**\n- **Over-refunding**: We do not `SUM()` existing refunds to check if they exceed the original order total. To reach Control requires complex serializable transactions or DB triggers. We accept Stripe acting as the successive check (Warning) here, as their API rejects refunds exceeding the charge amount.\n- **Stuck `PENDING` Records**: A crash mid-Stripe request leaves the database row stuck as `PENDING`. We accept this (Warning/Detection) because it's better to reconcile a known stuck record via a cron job than to lose it completely.\n\n---\n\n### 1. TypeScript Handler\n\n```typescript\nimport { z } from \"zod\";\nimport { PrismaClient } from \"@prisma/client\";\nimport Stripe from \"stripe\";\n\nconst prisma = new PrismaClient();\n// Assumption: Stripe secret is configured securely in the environment\nconst stripe = new Stripe(process.env.STRIPE_SECRET_KEY as string, { apiVersion: \"2024-04-10\" });\n\n// --- POKA-YOKE: C1. Branded Types ---\ndeclare const brand: unique symbol;\ntype Brand\u003cT, B\u003e = T \u0026 { readonly [brand]: B };\n\nexport type OrderId = Brand\u003cstring, \"OrderId\"\u003e;\nexport type TenantId = Brand\u003cstring, \"TenantId\"\u003e;\nexport type UserId = Brand\u003cstring, \"UserId\"\u003e;\nexport type IdempotencyKey = Brand\u003cstring, \"IdempotencyKey\"\u003e;\n\nexport type AuthenticatedSession = {\n  userId: UserId;\n  tenantId: TenantId;\n};\n\n// --- POKA-YOKE: C7 \u0026 C6. Parse, Don't Validate ---\nconst RefundRequestSchema = z.object({\n  orderId: z.string().uuid().brand\u003c\"OrderId\"\u003e(),\n  amountCents: z.number().int().positive(), \n  reason: z.string().min(1).max(255),\n  // M2: Required idempotency key, not optional\n  idempotencyKey: z.string().min(1).brand\u003c\"IdempotencyKey\"\u003e(),\n});\n\nexport async function createRefundHandler(req: any, res: any, session: AuthenticatedSession) {\n  // 1. Boundary Control: Discard untyped input immediately\n  const parsed = RefundRequestSchema.safeParse(req.body);\n  if (!parsed.success) {\n    return res.status(400).json({ error: parsed.error.format() });\n  }\n  const data = parsed.data;\n\n  // 2. Locate order and enforce tenant boundaries\n  const order = await prisma.order.findUnique({\n    where: {\n      id_tenantId: { id: data.orderId, tenantId: session.tenantId },\n    },\n  });\n\n  if (!order || !order.stripeChargeId) {\n    return res.status(404).json({ error: \"Order not found or missing charge ID\" });\n  }\n\n  // 3. Motion-step (F5): Record intent BEFORE external effects\n  let pendingRefund;\n  try {\n    pendingRefund = await prisma.refund.create({\n      data: {\n        orderId: data.orderId,\n        tenantId: session.tenantId,\n        amountCents: data.amountCents,\n        reason: data.reason,\n        idempotencyKey: data.idempotencyKey,\n        status: \"PENDING\",\n      },\n    });\n  } catch (error: any) {\n    // M5 (Check-then-act guard): Return the existing refund if the idempotency key was reused\n    if (error.code === \"P2002\") {\n      const existing = await prisma.refund.findUnique({\n        where: {\n          tenantId_idempotencyKey: {\n            tenantId: session.tenantId,\n            idempotencyKey: data.idempotencyKey,\n          },\n        },\n      });\n      return res.status(200).json(existing);\n    }\n    throw error;\n  }\n\n  // 4. Execute non-idempotent external call safely\n  let stripeRefund;\n  try {\n    stripeRefund = await stripe.refunds.create(\n      {\n        charge: order.stripeChargeId,\n        amount: data.amountCents,\n        reason: \"requested_by_customer\",\n      },\n      {\n        idempotencyKey: data.idempotencyKey, // M2: Pass the required key\n      }\n    );\n  } catch (stripeError) {\n    // X1: Do not swallow the error. Sync the state and re-throw.\n    await prisma.refund.update({\n      where: { id: pendingRefund.id },\n      data: { status: \"FAILED\" },\n    });\n    throw stripeError;\n  }\n\n  // 5. Finalize state\n  const finalizedRefund = await prisma.refund.update({\n    where: { id: pendingRefund.id },\n    data: { status: \"SUCCEEDED\" },\n  });\n\n  return res.status(200).json(finalizedRefund);\n}\n```\n\n### 2. Prisma Schema Additions\n\n```prisma\nmodel Order {\n  id             String   @id\n  tenantId       String\n  totalCents     Int\n  currency       String\n  stripeChargeId String?  // Assumption: Tracked for the payment \n\n  refunds        Refund[]\n\n  // DEVICE: Composite index enforces F6 Tenant Isolation in DB relationships\n  @@unique([id, tenantId])\n}\n\nmodel Refund {\n  id             String   @id @default(uuid())\n  orderId        String\n  amountCents    Int\n  reason         String\n  createdAt      DateTime @default(now())\n\n  // --- Devices Added ---\n  tenantId       String\n  idempotencyKey String\n  status         String   @default(\"PENDING\")\n\n  // Control (F6): A refund physically cannot be associated with a different tenant's order\n  order          Order    @relation(fields: [orderId, tenantId], references: [id, tenantId])\n\n  // Control (M5): Database-level guarantee against concurrent double requests\n  @@unique([tenantId, idempotencyKey])\n}\n```\n\n### 3. SQL Migration\n\n```sql\n-- 1. Order Setup: Support for the composite foreign key\nCREATE UNIQUE INDEX \"Order_id_tenantId_key\" ON \"Order\"(\"id\", \"tenantId\");\n\n-- 2. Refund Setup: Add new mistake-proofing columns\nALTER TABLE \"Refund\" ADD COLUMN \"tenantId\" TEXT NOT NULL;\nALTER TABLE \"Refund\" ADD COLUMN \"idempotencyKey\" TEXT NOT NULL;\nALTER TABLE \"Refund\" ADD COLUMN \"status\" TEXT NOT NULL DEFAULT 'PENDING';\n\n-- 3. Safety Constraints\n-- Enforce idempotency uniquely per tenant\nCREATE UNIQUE INDEX \"Refund_tenantId_idempotencyKey_key\" ON \"Refund\"(\"tenantId\", \"idempotencyKey\");\n\n-- Enforce tenant isolation structurally\nALTER TABLE \"Refund\" ADD CONSTRAINT \"Refund_orderId_tenantId_fkey\" \n  FOREIGN KEY (\"orderId\", \"tenantId\") REFERENCES \"Order\"(\"id\", \"tenantId\") ON DELETE RESTRICT ON UPDATE CASCADE;\n```","toolAction":"Finishing the request","toolSummary":"Finish request"}