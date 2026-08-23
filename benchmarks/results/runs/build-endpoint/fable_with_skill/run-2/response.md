Routing done: new code touching money + tenancy → `design` then `authz`. Building it now; the mistake-proofing is the code.

**Misuses enumerated before writing the signature**

1. Order loaded by `orderId` alone → cross-tenant refund (IDOR). 2. Retry / double-click / queue redelivery → double refund at Stripe. 3. Sum of refunds exceeds `totalCents`, racing under concurrency. 4. `reason` is free text but Stripe accepts three values. 5. Crash between "call Stripe" and "persist row" leaves money moved with no record. 6. `Refund` has no `tenantId`, so RLS and scoped queries can't cover it.

## `prisma/schema.prisma` additions

```prisma
enum RefundReason { duplicate fraudulent requested_by_customer }   // Stripe's closed set
enum RefundStatus { pending succeeded failed }

model Order {
  id                    String   @id @default(uuid()) @db.Uuid
  tenantId              String   @db.Uuid
  totalCents            Int
  refundedCents         Int      @default(0)          // NEW: running total, CHECK-bounded
  currency              String   @db.Char(3)
  stripePaymentIntentId String   @unique              // NEW (assumed; Stripe needs a target)
  refunds               Refund[]
  @@unique([id, tenantId])                            // target for the composite FK below
}

model Refund {
  id             String       @id @default(uuid()) @db.Uuid
  orderId        String       @db.Uuid
  tenantId       String       @db.Uuid               // NEW: denormalised so RLS/FK can bind it
  amountCents    Int
  reason         RefundReason
  status         RefundStatus @default(pending)
  idempotencyKey String
  requestHash    String                               // payload bound to the key
  stripeRefundId String?      @unique
  createdAt      DateTime     @default(now()) @db.Timestamptz
  order          Order        @relation(fields: [orderId, tenantId], references: [id, tenantId])
  @@unique([tenantId, idempotencyKey])
}
```

## `prisma/migrations/20260822_refunds/migration.sql`

```sql
CREATE TYPE "RefundReason" AS ENUM ('duplicate','fraudulent','requested_by_customer');
CREATE TYPE "RefundStatus" AS ENUM ('pending','succeeded','failed');

-- Order: expand only (no drops; contract in a later deploy if needed)
ALTER TABLE "Order"
  ADD COLUMN "refundedCents" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "stripePaymentIntentId" TEXT,                -- backfill, then SET NOT NULL in a follow-up
  ADD CONSTRAINT "Order_id_tenantId_key" UNIQUE ("id","tenantId"),
  ADD CONSTRAINT "Order_refund_bound" CHECK ("refundedCents" >= 0 AND "refundedCents" <= "totalCents");
CREATE UNIQUE INDEX "Order_stripePaymentIntentId_key" ON "Order"("stripePaymentIntentId");

-- Refund: add tenantId, backfill from the parent, then lock it down
ALTER TABLE "Refund"
  ADD COLUMN "tenantId" UUID,
  ADD COLUMN "status" "RefundStatus" NOT NULL DEFAULT 'succeeded',  -- legacy rows were real
  ADD COLUMN "idempotencyKey" TEXT,
  ADD COLUMN "requestHash" TEXT,
  ADD COLUMN "stripeRefundId" TEXT;
UPDATE "Refund" r SET "tenantId" = o."tenantId" FROM "Order" o WHERE o.id = r."orderId";
UPDATE "Refund" SET "idempotencyKey" = 'legacy:' || id, "requestHash" = '' WHERE "idempotencyKey" IS NULL;
ALTER TABLE "Refund"
  ALTER COLUMN "tenantId" SET NOT NULL,
  ALTER COLUMN "idempotencyKey" SET NOT NULL,
  ALTER COLUMN "requestHash" SET NOT NULL,
  ALTER COLUMN "status" DROP DEFAULT,
  ALTER COLUMN "reason" TYPE "RefundReason" USING "reason"::"RefundReason",
  ADD CONSTRAINT "Refund_amount_positive" CHECK ("amountCents" > 0),
  -- a succeeded refund without a Stripe id has no spelling
  ADD CONSTRAINT "Refund_status_shape" CHECK (
    ("status" = 'succeeded' AND "stripeRefundId" IS NOT NULL) OR
    ("status" <> 'succeeded' AND "stripeRefundId" IS NULL)),
  -- a Refund cannot reference an Order from another tenant
  ADD CONSTRAINT "Refund_order_fkey" FOREIGN KEY ("orderId","tenantId")
    REFERENCES "Order"("id","tenantId") ON DELETE RESTRICT;
CREATE UNIQUE INDEX "Refund_tenantId_idempotencyKey_key" ON "Refund"("tenantId","idempotencyKey");
CREATE UNIQUE INDEX "Refund_stripeRefundId_key" ON "Refund"("stripeRefundId");

-- Row-level security: holds for psql, scripts, and code not yet written
ALTER TABLE "Order"  ENABLE ROW LEVEL SECURITY; ALTER TABLE "Order"  FORCE ROW LEVEL SECURITY;
ALTER TABLE "Refund" ENABLE ROW LEVEL SECURITY; ALTER TABLE "Refund" FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON "Order"
  USING ("tenantId" = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation ON "Refund"
  USING ("tenantId" = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK ("tenantId" = current_setting('app.tenant_id', true)::uuid);
```

## `src/refunds/handler.ts`

```ts
import { z } from "zod";
import { createHash } from "node:crypto";
import Stripe from "stripe";
import { PrismaClient, Prisma, Refund, RefundStatus } from "@prisma/client";

// ---- Branded types: an OrderId cannot be passed where a TenantId goes ----
const TenantId = z.string().uuid().brand<"TenantId">();
const UserId   = z.string().uuid().brand<"UserId">();
const OrderId  = z.string().uuid().brand<"OrderId">();
const IdempotencyKey = z.string().min(8).max(128).brand<"IdempotencyKey">();
type TenantId = z.infer<typeof TenantId>;
type OrderId  = z.infer<typeof OrderId>;
type IdempotencyKey = z.infer<typeof IdempotencyKey>;

const Session = z.object({ userId: UserId, tenantId: TenantId });
const RefundBody = z.object({
  orderId: OrderId,
  amountCents: z.number().int().positive().max(10_000_000_00),
  reason: z.enum(["duplicate", "fraudulent", "requested_by_customer"]),
}).strict();
type RefundBody = z.infer<typeof RefundBody>;

// ---- Tenant-scoped transaction: the ONLY way handlers reach the database ----
// Sets the RLS variable per-transaction (is_local=true) so a pooled connection
// never carries a previous request's tenant.
async function tenantTx<T>(
  db: PrismaClient, tenantId: TenantId,
  fn: (tx: Prisma.TransactionClient) => Promise<T>,
): Promise<T> {
  return db.$transaction(async (tx) => {
    await tx.$executeRaw`SELECT set_config('app.tenant_id', ${tenantId}, true)`;
    return fn(tx);
  }, { isolationLevel: Prisma.TransactionIsolationLevel.ReadCommitted });
}

class HttpError extends Error {
  constructor(readonly status: number, message: string) { super(message); }
}

export function makeRefundHandler(db: PrismaClient, stripe: Stripe) {
  // Express-shaped; swap req/res types for your framework.
  return async function postRefund(req: any, res: any) {
    try {
      const session = Session.parse(req.session);                 // proof, not a boolean
      const key = IdempotencyKey.safeParse(req.get("Idempotency-Key"));
      if (!key.success) throw new HttpError(400, "Idempotency-Key header is required");
      const body = RefundBody.safeParse(req.body);
      if (!body.success) throw new HttpError(400, body.error.message);

      const refund = await createRefund(db, stripe, session.tenantId, key.data, body.data);
      res.status(refund.status === "succeeded" ? 201 : 202).json(refund);
    } catch (e) {
      if (e instanceof HttpError) return res.status(e.status).json({ error: e.message });
      throw e;                                                    // no silent fallback
    }
  };
}

export async function createRefund(
  db: PrismaClient, stripe: Stripe,
  tenantId: TenantId, key: IdempotencyKey, body: RefundBody,
): Promise<Refund> {
  const requestHash = createHash("sha256").update(JSON.stringify(body)).digest("hex");

  // Step 1 — reserve: idempotency row + amount headroom, in one transaction.
  const { refund, paymentIntentId } = await tenantTx(db, tenantId, async (tx) => {
    const existing = await tx.refund.findUnique({
      where: { tenantId_idempotencyKey: { tenantId, idempotencyKey: key } },
      include: { order: { select: { stripePaymentIntentId: true } } },
    });
    if (existing) {
      if (existing.requestHash !== requestHash)
        throw new HttpError(422, "Idempotency-Key reused with a different payload");
      if (existing.status === "failed")
        throw new HttpError(409, "This refund attempt failed; use a new Idempotency-Key");
      // succeeded → replay; pending → re-drive the Stripe step below (converges)
      return { refund: existing, paymentIntentId: existing.order.stripePaymentIntentId };
    }

    // Atomic check-and-reserve. Column-vs-column compare needs raw SQL; the
    // Order_refund_bound CHECK backs it even if this query is bypassed.
    const reserved = await tx.$executeRaw`
      UPDATE "Order" SET "refundedCents" = "refundedCents" + ${body.amountCents}
      WHERE "id" = ${body.orderId}::uuid AND "tenantId" = ${tenantId}::uuid
        AND "refundedCents" + ${body.amountCents} <= "totalCents"`;
    if (reserved === 0) {
      const order = await tx.order.findFirst({ where: { id: body.orderId, tenantId } });
      if (!order) throw new HttpError(404, "Order not found");   // 404, never 403
      throw new HttpError(422, `Refund exceeds remaining ${order.totalCents - order.refundedCents} cents`);
    }
    const order = await tx.order.findFirstOrThrow({ where: { id: body.orderId, tenantId } });
    if (!order.stripePaymentIntentId) throw new HttpError(422, "Order has no Stripe payment");

    const refund = await tx.refund.create({
      data: { orderId: body.orderId, tenantId, amountCents: body.amountCents,
              reason: body.reason, status: "pending", idempotencyKey: key, requestHash },
    });
    return { refund, paymentIntentId: order.stripePaymentIntentId };
  });
  if (refund.status === "succeeded") return refund;

  // Step 2 — external effect, keyed on OUR row id so every re-drive hits the same Stripe op.
  let stripeRefund: Stripe.Refund;
  try {
    stripeRefund = await stripe.refunds.create(
      { payment_intent: paymentIntentId, amount: refund.amountCents, reason: refund.reason },
      { idempotencyKey: `refund:${refund.id}` },
    );
  } catch (err) {
    if (err instanceof Stripe.errors.StripeCardError || err instanceof Stripe.errors.StripeInvalidRequestError) {
      // Terminal at Stripe: release the headroom and record the failure.
      await tenantTx(db, tenantId, async (tx) => {
        await tx.refund.update({ where: { id: refund.id }, data: { status: "failed" } });
        await tx.order.update({ where: { id: refund.orderId },
          data: { refundedCents: { decrement: refund.amountCents } } });
      });
      throw new HttpError(422, `Stripe rejected the refund: ${err.message}`);
    }
    throw err;  // network/5xx: row stays pending; client retries with the same key and converges
  }

  // Step 3 — finalize.
  return tenantTx(db, tenantId, (tx) =>
    tx.refund.update({ where: { id: refund.id },
      data: { status: "succeeded", stripeRefundId: stripeRefund.id } }));
}

// Exhaustiveness guard for anyone rendering status later
export function assertNever(x: never): never { throw new Error(`Unhandled: ${JSON.stringify(x)}`); }
export const _statusCheck = (s: RefundStatus) => {
  switch (s) { case "pending": case "succeeded": case "failed": return; default: return assertNever(s); }
};
```

`★ Insight ─────────────────────────────────────`
- The Stripe idempotency key is derived from **our** row id, not the client's header. The client key → row mapping is enforced by the DB unique index, so any retry lands on the same row and therefore the same Stripe operation — two layers, one identity.
- `refundedCents` is a denormalised counter on purpose: it turns "sum of refunds ≤ total" (unenforceable as a `CHECK`) into a single-row invariant the database *can* enforce.
`─────────────────────────────────────────────────`

## What this makes impossible, and at which rung

| Misuse | Device | Rung |
|---|---|---|
| Refunding another tenant's order | Tenant comes from session only; scoped `findFirst`; composite FK `(orderId, tenantId)`; RLS with `FORCE` | Control |
| Double refund on retry | Required `Idempotency-Key` → unique `(tenantId, key)`, payload hash bound, Stripe key = row id | Control |
| Over-refund under concurrency | Atomic conditional `UPDATE` + `Order_refund_bound CHECK` | Control |
| Bad `reason`, non-integer / negative amount | Zod enum + DB enum; `CHECK amountCents > 0` | Control |
| "Succeeded" row without a Stripe id | `Refund_status_shape CHECK` | Control |
| Leaked `tenant_id` across pooled connections | `set_config(..., true)` inside every transaction | Control |

**Left possible, on purpose:** a process crash after Stripe succeeds but before step 3 leaves a `pending` row with money moved — the same client key re-drives and converges, but an abandoned key needs a **reconciliation job** (Detection rung) that lists `pending` rows older than N minutes and queries Stripe by `refund:<id>`. Also `stripePaymentIntentId` is nullable in the migration until you backfill it; follow up with `SET NOT NULL`. And the two-tenant 404 test (authz skill's Detection device) still needs writing — it is what proves the RLS policy is actually in force.

Assumptions made: Express-style `req/res`, Zod available, `Order` gains `stripePaymentIntentId`, and the DB role your app connects with is not a superuser (RLS is bypassed for superusers).