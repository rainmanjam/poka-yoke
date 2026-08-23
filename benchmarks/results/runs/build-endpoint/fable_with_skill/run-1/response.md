Done reading. Router → `design` (new interface touching money) then `authz` (tenant-scoped endpoint). Following design's ritual — enumerate misuse first, then shape the code so it can't be expressed — and building the scoping rather than reporting on it.

## Misuses enumerated before writing the signature

| # | Mistake a caller/retry/attacker can make | Device | Rung |
|---|---|---|---|
| 1 | `orderId` from another tenant (IDOR) | Order loaded only via `{ id, tenantId: session.tenantId }`; 404 never 403 | Control |
| 2 | Refund more than the order total, or partial refunds that *sum* past it | `SELECT … FOR UPDATE` on the order + sum of non-failed refunds, inside one transaction; `CHECK (amount_cents > 0)` | Control |
| 3 | Retry / double-click / queue redelivery refunds twice | **Required** `Idempotency-Key`; unique `(tenant_id, idempotency_key)`; same key forwarded to Stripe; payload hash stored so a reused key with a different body is rejected, not silently replayed | Control |
| 4 | Crash between Stripe success and our DB write | Row reserved as `pending` *before* the Stripe call; retry replays Stripe with the same key, Stripe returns the same refund, we finalize | Control |
| 5 | `reason` as free text → Stripe rejects / reporting garbage | Literal union mapped to Stripe's enum | Control |
| 6 | Swapping `userId`/`tenantId`/`orderId` (all strings) | Branded zod types | Control |
| 7 | Refund against an order that never had a Stripe payment | `stripePaymentIntentId` is nullable (existing rows) — handler refuses with 409 | Warning (see closing note) |
| 8 | `status` + `stripeRefundId` bag-of-optionals | DB `CHECK` ties `stripe_refund_id IS NOT NULL` to `status = 'succeeded'` | Control |

## `prisma/schema.prisma` additions

```prisma
enum RefundStatus {
  pending
  succeeded
  failed
}

enum RefundReason {
  duplicate
  fraudulent
  requested_by_customer
}

model Order {
  id                    String   @id @default(uuid()) @db.Uuid
  tenantId              String   @map("tenant_id") @db.Uuid
  totalCents            Int      @map("total_cents")
  currency              String   @db.Char(3)
  // NEW — nullable because existing rows predate it; the handler refuses to refund
  // an order that lacks one (hazard #7).
  stripePaymentIntentId String?  @unique @map("stripe_payment_intent_id")
  refunds               Refund[]

  @@index([tenantId])
  @@map("orders")
}

model Refund {
  id                String       @id @default(uuid()) @db.Uuid
  orderId           String       @map("order_id") @db.Uuid
  // NEW — denormalised so the unique idempotency index and RLS can be expressed
  // on this table without a join.
  tenantId          String       @map("tenant_id") @db.Uuid
  amountCents       Int          @map("amount_cents")
  reason            RefundReason
  status            RefundStatus @default(pending)
  idempotencyKey    String       @map("idempotency_key")
  // sha256 of the canonical request body; a reused key with a different body is an error.
  requestHash       String       @map("request_hash") @db.Char(64)
  stripeRefundId    String?      @unique @map("stripe_refund_id")
  failureReason     String?      @map("failure_reason")
  requestedByUserId String       @map("requested_by_user_id") @db.Uuid
  createdAt         DateTime     @default(now()) @map("created_at") @db.Timestamptz
  updatedAt         DateTime     @updatedAt @map("updated_at") @db.Timestamptz

  order Order @relation(fields: [orderId], references: [id])

  @@unique([tenantId, idempotencyKey])
  @@index([orderId])
  @@map("refunds")
}
```

## `prisma/migrations/20260822000000_add_refund_idempotency/migration.sql`

```sql
CREATE TYPE "RefundStatus" AS ENUM ('pending', 'succeeded', 'failed');
CREATE TYPE "RefundReason" AS ENUM ('duplicate', 'fraudulent', 'requested_by_customer');

ALTER TABLE "orders"
  ADD COLUMN "stripe_payment_intent_id" TEXT;
CREATE UNIQUE INDEX "orders_stripe_payment_intent_id_key"
  ON "orders" ("stripe_payment_intent_id");

-- Expand step. Existing refund rows are backfilled from their order; the new
-- columns become NOT NULL only after the backfill so the migration cannot half-apply.
ALTER TABLE "refunds"
  ADD COLUMN "tenant_id"             UUID,
  ADD COLUMN "status"                "RefundStatus" NOT NULL DEFAULT 'succeeded',
  ADD COLUMN "idempotency_key"       TEXT,
  ADD COLUMN "request_hash"          CHAR(64),
  ADD COLUMN "stripe_refund_id"      TEXT,
  ADD COLUMN "failure_reason"        TEXT,
  ADD COLUMN "requested_by_user_id"  UUID,
  ADD COLUMN "updated_at"            TIMESTAMPTZ NOT NULL DEFAULT now();

UPDATE "refunds" r
   SET "tenant_id"            = o."tenant_id",
       "idempotency_key"      = 'legacy:' || r."id"::text,
       "request_hash"         = repeat('0', 64),
       "requested_by_user_id" = '00000000-0000-0000-0000-000000000000'
  FROM "orders" o
 WHERE o."id" = r."order_id";

ALTER TABLE "refunds"
  ALTER COLUMN "tenant_id"            SET NOT NULL,
  ALTER COLUMN "idempotency_key"      SET NOT NULL,
  ALTER COLUMN "request_hash"         SET NOT NULL,
  ALTER COLUMN "requested_by_user_id" SET NOT NULL,
  ALTER COLUMN "status"               DROP DEFAULT,
  ALTER COLUMN "status"               SET DEFAULT 'pending',
  ALTER COLUMN "reason" TYPE "RefundReason" USING "reason"::"RefundReason";

-- Devices that hold even from psql:
ALTER TABLE "refunds"
  ADD CONSTRAINT "refunds_amount_positive" CHECK ("amount_cents" > 0),
  ADD CONSTRAINT "refunds_stripe_id_matches_status" CHECK (
    ("status" = 'succeeded' AND "stripe_refund_id" IS NOT NULL)
    OR ("status" <> 'succeeded' AND "stripe_refund_id" IS NULL)
  );

CREATE UNIQUE INDEX "refunds_tenant_id_idempotency_key_key"
  ON "refunds" ("tenant_id", "idempotency_key");
CREATE UNIQUE INDEX "refunds_stripe_refund_id_key"
  ON "refunds" ("stripe_refund_id");
CREATE INDEX "refunds_order_id_idx" ON "refunds" ("order_id");
CREATE INDEX "orders_tenant_id_idx" ON "orders" ("tenant_id");

-- Row-level security: protects paths this handler does not own (scripts, future services).
ALTER TABLE "refunds" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "refunds" FORCE ROW LEVEL SECURITY;
CREATE POLICY "refunds_tenant_isolation" ON "refunds"
  USING ("tenant_id" = current_setting('app.tenant_id', true)::uuid);
ALTER TABLE "orders" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "orders" FORCE ROW LEVEL SECURITY;
CREATE POLICY "orders_tenant_isolation" ON "orders"
  USING ("tenant_id" = current_setting('app.tenant_id', true)::uuid);
```

## `src/refunds/types.ts`

```ts
import { z } from "zod";

// Branded IDs: swapping orderId/userId/tenantId no longer compiles (hazard #6).
export const TenantId = z.string().uuid().brand<"TenantId">();
export const UserId = z.string().uuid().brand<"UserId">();
export const OrderId = z.string().uuid().brand<"OrderId">();
export const IdempotencyKey = z.string().min(16).max(255).brand<"IdempotencyKey">();

export type TenantId = z.infer<typeof TenantId>;
export type UserId = z.infer<typeof UserId>;
export type OrderId = z.infer<typeof OrderId>;
export type IdempotencyKey = z.infer<typeof IdempotencyKey>;

// Closed set, mirrors Stripe's enum exactly (hazard #5).
export const RefundReason = z.enum(["duplicate", "fraudulent", "requested_by_customer"]);
export type RefundReason = z.infer<typeof RefundReason>;

export const RefundRequest = z.object({
  orderId: OrderId,
  amountCents: z.number().int().positive().max(100_000_000), // F7: bounded
  reason: RefundReason,
}).strict();
export type RefundRequest = z.infer<typeof RefundRequest>;

export const Session = z.object({ userId: UserId, tenantId: TenantId });
export type Session = z.infer<typeof Session>;

// Discriminated union for the outcome — no "succeeded with an error" state.
export type RefundOutcome =
  | { kind: "created"; refund: RefundView }
  | { kind: "replayed"; refund: RefundView }
  | { kind: "order_not_found" }
  | { kind: "order_not_refundable"; detail: string }
  | { kind: "exceeds_refundable"; refundableCents: number }
  | { kind: "idempotency_conflict" }
  | { kind: "stripe_declined"; detail: string };

export type RefundView = {
  id: string;
  orderId: OrderId;
  amountCents: number;
  currency: string;
  reason: RefundReason;
  status: "pending" | "succeeded" | "failed";
  stripeRefundId: string | null;
  createdAt: string;
};
```

## `src/refunds/service.ts`

```ts
import { createHash } from "node:crypto";
import { Prisma, PrismaClient, Refund } from "@prisma/client";
import Stripe from "stripe";
import {
  IdempotencyKey, OrderId, RefundOutcome, RefundRequest, RefundView, Session, TenantId,
} from "./types";

function hashRequest(req: RefundRequest): string {
  return createHash("sha256")
    .update(JSON.stringify({ o: req.orderId, a: req.amountCents, r: req.reason }))
    .digest("hex");
}

function toView(r: Refund, currency: string): RefundView {
  return {
    id: r.id, orderId: r.orderId as OrderId, amountCents: r.amountCents, currency,
    reason: r.reason, status: r.status, stripeRefundId: r.stripeRefundId,
    createdAt: r.createdAt.toISOString(),
  };
}

/**
 * Tenant-scoped refund service. There is no constructor without a tenant, so an
 * unscoped query cannot be written from here (authz device #2).
 */
export class RefundService {
  constructor(
    private readonly db: PrismaClient,
    private readonly stripe: Stripe,
    private readonly session: Session,
  ) {}

  async create(req: RefundRequest, key: IdempotencyKey): Promise<RefundOutcome> {
    const { tenantId, userId } = this.session;
    const requestHash = hashRequest(req);

    // ── Phase 1: reserve the refund row in one transaction ────────────────────
    // Everything a concurrent request could race on is decided here, under a row
    // lock on the order. The Stripe call happens AFTER commit so an external
    // timeout cannot hold a DB lock, and a crash after Stripe leaves a replayable
    // 'pending' row rather than a lost refund (hazards #2, #3, #4).
    const reserved = await this.db.$transaction(async (tx) => {
      await tx.$executeRaw`SELECT set_config('app.tenant_id', ${tenantId}, true)`;

      // Scoped by session tenant, never by anything in the body (hazard #1).
      const [order] = await tx.$queryRaw<
        { id: string; totalCents: number; currency: string; stripePaymentIntentId: string | null }[]
      >`
        SELECT id, total_cents AS "totalCents", currency,
               stripe_payment_intent_id AS "stripePaymentIntentId"
          FROM orders
         WHERE id = ${req.orderId}::uuid AND tenant_id = ${tenantId}::uuid
           FOR UPDATE`;
      if (!order) return { kind: "order_not_found" } as const;

      // Idempotent replay: same key + same body → return the existing row.
      const existing = await tx.refund.findUnique({
        where: { tenantId_idempotencyKey: { tenantId, idempotencyKey: key } },
      });
      if (existing) {
        if (existing.requestHash !== requestHash) return { kind: "idempotency_conflict" } as const;
        return { kind: "existing", refund: existing, order } as const;
      }

      if (!order.stripePaymentIntentId) {
        return { kind: "order_not_refundable", detail: "order has no Stripe payment" } as const;
      }

      const { _sum } = await tx.refund.aggregate({
        _sum: { amountCents: true },
        where: { orderId: order.id, tenantId, status: { not: "failed" } },
      });
      const refundableCents = order.totalCents - (_sum.amountCents ?? 0);
      if (req.amountCents > refundableCents) {
        return { kind: "exceeds_refundable", refundableCents } as const;
      }

      const refund = await tx.refund.create({
        data: {
          orderId: order.id, tenantId, amountCents: req.amountCents, reason: req.reason,
          status: "pending", idempotencyKey: key, requestHash, requestedByUserId: userId,
        },
      });
      return { kind: "fresh", refund, order } as const;
    }, { isolationLevel: Prisma.TransactionIsolationLevel.ReadCommitted });

    switch (reserved.kind) {
      case "order_not_found":
      case "order_not_refundable":
      case "exceeds_refundable":
      case "idempotency_conflict":
        return reserved;
      case "existing":
        if (reserved.refund.status !== "pending") {
          return { kind: "replayed", refund: toView(reserved.refund, reserved.order.currency) };
        }
        // A pending row means an earlier attempt died mid-flight; fall through and
        // re-drive Stripe with the same key — Stripe will return the same refund.
        return this.settle(reserved.refund, reserved.order, key, "replayed");
      case "fresh":
        return this.settle(reserved.refund, reserved.order, key, "created");
      default:
        return assertNever(reserved);
    }
  }

  // ── Phase 2: call Stripe, then finalize the row ────────────────────────────
  private async settle(
    refund: Refund,
    order: { stripePaymentIntentId: string | null; currency: string },
    key: IdempotencyKey,
    kind: "created" | "replayed",
  ): Promise<RefundOutcome> {
    let stripeRefund: Stripe.Refund;
    try {
      stripeRefund = await this.stripe.refunds.create(
        {
          payment_intent: order.stripePaymentIntentId ?? undefined,
          amount: refund.amountCents,
          reason: refund.reason,
          metadata: { refundId: refund.id, tenantId: refund.tenantId, orderId: refund.orderId },
        },
        // Same key as our DB row: a retry replays Stripe's stored response (hazard #3/#4).
        { idempotencyKey: `refund:${refund.tenantId}:${key}` },
      );
    } catch (err) {
      if (err instanceof Stripe.errors.StripeCardError || err instanceof Stripe.errors.StripeInvalidRequestError) {
        // Terminal decline: record it so the amount is released from the refundable sum.
        await this.db.refund.update({
          where: { id: refund.id },
          data: { status: "failed", failureReason: err.message },
        });
        return { kind: "stripe_declined", detail: err.message };
      }
      throw err; // network/5xx: leave 'pending'; the client retries with the same key.
    }

    const updated = await this.db.refund.update({
      where: { id: refund.id },
      data: { status: "succeeded", stripeRefundId: stripeRefund.id },
    });
    return { kind, refund: toView(updated, order.currency) };
  }
}

function assertNever(x: never): never {
  throw new Error(`Unhandled variant: ${JSON.stringify(x)}`);
}
```

## `src/refunds/handler.ts` (Express)

```ts
import type { Request, Response } from "express";
import { PrismaClient } from "@prisma/client";
import Stripe from "stripe";
import { RefundService } from "./service";
import { IdempotencyKey, RefundRequest, Session } from "./types";

const db = new PrismaClient();
const stripe = new Stripe(requireEnv("STRIPE_SECRET_KEY"), { apiVersion: "2025-06-30.basil" });

function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v) throw new Error(`Missing required env var ${name}`); // fails the boot, not the 3am request
  return v;
}

export async function postRefund(req: Request, res: Response): Promise<void> {
  // Parse, don't validate — everything past this line holds branded, proven types.
  const session = Session.safeParse(req.session);
  if (!session.success) { res.status(401).end(); return; }

  const key = IdempotencyKey.safeParse(req.header("Idempotency-Key"));
  if (!key.success) {
    res.status(400).json({ error: "Idempotency-Key header is required (16–255 chars)" });
    return;
  }

  const body = RefundRequest.safeParse(req.body);
  if (!body.success) { res.status(400).json({ error: body.error.flatten() }); return; }

  const outcome = await new RefundService(db, stripe, session.data).create(body.data, key.data);

  switch (outcome.kind) {
    case "created":   res.status(201).json(outcome.refund); return;
    case "replayed":  res.status(200).json(outcome.refund); return;
    case "order_not_found":  res.status(404).end(); return; // 404, not 403 — don't confirm existence
    case "order_not_refundable": res.status(409).json({ error: outcome.detail }); return;
    case "exceeds_refundable":
      res.status(422).json({ error: "amount exceeds refundable balance", refundableCents: outcome.refundableCents });
      return;
    case "idempotency_conflict":
      res.status(422).json({ error: "Idempotency-Key was already used with a different request body" });
      return;
    case "stripe_declined": res.status(402).json({ error: outcome.detail }); return;
    default: return assertNever(outcome);
  }
}

function assertNever(x: never): never {
  throw new Error(`Unhandled variant: ${JSON.stringify(x)}`);
}
```

Route registration: `router.post("/refunds", requireAuth, requireRole("refunds:create"), postRefund)`.

`★ Insight ─────────────────────────────────────`
- The two-phase shape (reserve row → commit → Stripe → finalize) is the part most refund handlers get backwards. Calling Stripe *inside* the transaction means a 30s Stripe timeout holds a row lock on the order; calling it with no prior row means a crash after Stripe succeeds loses the refund entirely. The `pending` row is the motion-step sensor.
- Reusing *our* idempotency key as *Stripe's* is what makes the crash recovery free: the retry hits Stripe with the same key and Stripe hands back the original refund instead of creating another.
`─────────────────────────────────────────────────`

## Closing note — what is impossible, and what I left possible

**Impossible now (Control):** cross-tenant refund (session-scoped load + RLS), over-refund under concurrency (`FOR UPDATE` + summed check), double refund on retry (required key + unique index + Stripe key), silent replay with a different body (request hash), a `succeeded` row with no Stripe ID (DB `CHECK`), negative/zero amounts (`CHECK`), an unhandled outcome variant (`assertNever`).

**Left possible, deliberately:**
- `stripePaymentIntentId` is nullable — existing orders have no value. Control would require a backfill I can't write without your data; the handler refuses with 409 instead (Warning). Once backfilled, make it `NOT NULL`.
- Who may refund is delegated to `requireRole` middleware, not encoded in the type. An `Authorized<Session>` brand would reach Control; I assumed your router already has default-deny policy declaration.
- The over-refund sum is enforced in the transaction, not the database. A trigger would hold against `psql`; I judged it not worth the opacity for a single write path. Say the word and I'll add it.
- RLS only works if *every* connection sets `app.tenant_id`. I set it per-transaction here; if your pool is shared with unscoped code, a Prisma `$extends` that injects it on every query is the next device.

**Assumptions:** Express, zod, Stripe SDK ≥ 17, UUID IDs, Postgres ≥ 12, `strict: true` with `tsc --noEmit` in CI (without that, the brands are comments). Last: the pending-row recovery path above is a check that must be *proven to fail* — the test worth writing first is "kill the process between Stripe success and the finalize update, retry with the same key, assert exactly one Stripe refund exists."