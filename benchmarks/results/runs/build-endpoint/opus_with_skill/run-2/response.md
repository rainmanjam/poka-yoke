Routed: **`design`** (new interface, money + multi-tenant), composed with **`authz`** for the tenant-scoping devices. Read `poka-yoke` → `design` → `hazard-catalog` → `lang-typescript` → `authz`.

## Misuse enumerated before the signature

| # | Misuse the obvious version permits | Catalog |
|---|---|---|
| 1 | `refund(orderId, tenantId, userId)` — three `string`s, any order compiles | C1/C3 |
| 2 | Refunding another tenant's order by passing its id | authz |
| 3 | `tenantId` taken from the request body instead of the session | authz |
| 4 | Retry / double-click / queue redelivery → two Stripe refunds | M2 |
| 5 | Refunding more than the order total, or racing two partials past a `SELECT sum()` check | M5/F6 |
| 6 | Stripe succeeds, DB write fails → money out, no row | F5 |
| 7 | `reason: string` — typo reaches Stripe, or a new reason silently falls through | C4/F1 |
| 8 | `amountCents` negative, zero, float, or 2^31 | C6/F7 |
| 9 | Refund row in a currency the order isn't in | C5 |
| 10 | `STRIPE_SECRET_KEY` missing, discovered on the first refund at 3am | F4 |

---

## `src/domain/ids.ts` — contact lens

```ts
import { z } from "zod";

/** Branded primitives. Zero runtime cost; makes arg-swapping a compile error. */
export const TenantId = z.string().uuid().brand<"TenantId">();
export type TenantId = z.infer<typeof TenantId>;

export const UserId = z.string().uuid().brand<"UserId">();
export type UserId = z.infer<typeof UserId>;

export const OrderId = z.string().uuid().brand<"OrderId">();
export type OrderId = z.infer<typeof OrderId>;

export const RefundId = z.string().uuid().brand<"RefundId">();
export type RefundId = z.infer<typeof RefundId>;

/** Stripe caps idempotency keys at 255; a short key is usually a client bug. */
export const IdempotencyKey = z.string().min(16).max(200).brand<"IdempotencyKey">();
export type IdempotencyKey = z.infer<typeof IdempotencyKey>;

/** Money is an integer count of minor units. Never a float, never bare `number`. */
export const Cents = z.number().int().positive().brand<"Cents">();
export type Cents = z.infer<typeof Cents>;

export const Currency = z.string().regex(/^[A-Z]{3}$/).brand<"Currency">();
export type Currency = z.infer<typeof Currency>;

export function assertNever(x: never): never {
  throw new Error(`Unhandled variant: ${JSON.stringify(x)}`);
}
```

`★ Insight ─────────────────────────────────────`
- `z.brand()` is stronger than `type OrderId = string`: TypeScript is structurally typed, so an unbranded alias is a comment. The brand is a phantom property, so the *only* way to obtain an `OrderId` short of an `as` cast is to have parsed one.
- Making `Cents` `.positive()` at the parser means every downstream signature taking `Cents` is proven non-negative — no re-checking, no "did someone already validate this?"
`─────────────────────────────────────────────────`

## `src/domain/refund.ts` — closed sets + exhaustive mapping

```ts
import { z } from "zod";
import { assertNever } from "./ids";

/** Our vocabulary, which is deliberately wider than Stripe's three values. */
export const RefundReason = z.enum([
  "duplicate",
  "fraudulent",
  "requested_by_customer",
  "order_canceled",
  "goodwill",
]);
export type RefundReason = z.infer<typeof RefundReason>;

export type StripeReason = "duplicate" | "fraudulent" | "requested_by_customer";

/**
 * Adding a reason next year breaks THIS BUILD rather than silently sending
 * an unmapped string to Stripe. That is the entire point of the never arm.
 */
export function toStripeReason(reason: RefundReason): StripeReason {
  switch (reason) {
    case "duplicate":             return "duplicate";
    case "fraudulent":            return "fraudulent";
    case "requested_by_customer": return "requested_by_customer";
    case "order_canceled":        return "requested_by_customer";
    case "goodwill":              return "requested_by_customer";
    default:                      return assertNever(reason);
  }
}

export type RefundStatus = "pending" | "succeeded" | "failed";
```

## `src/config.ts` — fixed-value at boot (F4)

```ts
import { z } from "zod";

const Env = z.object({
  DATABASE_URL: z.string().url(),
  STRIPE_SECRET_KEY: z.string().regex(/^sk_(test|live)_/),
  /** Hard ceiling per refund request. No default that is wrong for a payments service. */
  MAX_REFUND_CENTS: z.coerce.number().int().positive(),
  /** How long a pending refund may sit before the reconciler adopts it. */
  REFUND_RECONCILE_AFTER_MS: z.coerce.number().int().positive(),
});

const parsed = Env.safeParse(process.env);
if (!parsed.success) {
  // Fails the deploy, not the 3am refund.
  console.error("Invalid environment:", parsed.error.flatten().fieldErrors);
  process.exit(1);
}
export const config = parsed.data;
```

## `src/db/tenantScope.ts` — the unscoped query is unwritable

```ts
import { Prisma, PrismaClient } from "@prisma/client";
import type { TenantId } from "../domain/ids";

/**
 * The ONLY handle handlers get to the database. There is no constructor without
 * a TenantId, and the raw PrismaClient is lint-banned outside src/db/.
 * Every method below is transactional and sets app.tenant_id for RLS.
 */
export class TenantScope {
  private constructor(
    readonly tenantId: TenantId,
    readonly tx: Prisma.TransactionClient,
  ) {}

  static async transaction<T>(
    db: PrismaClient,
    tenantId: TenantId,
    fn: (scope: TenantScope) => Promise<T>,
  ): Promise<T> {
    return db.$transaction(async (tx) => {
      // `true` = SET LOCAL semantics: scoped to this transaction, so a pooled
      // connection can never carry a previous request's tenant into this one.
      await tx.$executeRaw`SELECT set_config('app.tenant_id', ${tenantId}::text, true)`;
      return fn(new TenantScope(tenantId, tx));
    });
  }
}
```

`★ Insight ─────────────────────────────────────`
- The device is not the `WHERE tenantId = ?` clause — it's that a handler has no reference to anything that could omit one. Compare the two lines in the authz skill: whichever form is *shorter* is the one that gets written under deadline, so the safe form has to be the short one.
- `set_config(..., true)` is the difference between working RLS and a cross-tenant leak with extra steps. `SET` (session-scoped) on a PgBouncer transaction-pooled connection outlives the request.
`─────────────────────────────────────────────────`

## `src/services/createRefund.ts` — the core

```ts
import { Prisma, PrismaClient } from "@prisma/client";
import Stripe from "stripe";
import { createHash } from "node:crypto";
import { config } from "../config";
import { TenantScope } from "../db/tenantScope";
import { toStripeReason, type RefundReason } from "../domain/refund";
import {
  assertNever, type Cents, type Currency, type IdempotencyKey,
  type OrderId, type RefundId, type TenantId, type UserId,
} from "../domain/ids";

/** Every field required. No optional idempotency key — an optional one is rung zero. */
export interface CreateRefundInput {
  readonly tenantId: TenantId;          // from the session, never the body
  readonly actorId: UserId;             // from the session, never the body
  readonly orderId: OrderId;
  readonly amountCents: Cents;
  readonly reason: RefundReason;
  readonly idempotencyKey: IdempotencyKey;
}

export interface RefundView {
  id: RefundId; orderId: OrderId; amountCents: number; currency: Currency;
  reason: RefundReason; status: "succeeded" | "pending" | "failed";
  stripeRefundId: string | null; failureCode: string | null; createdAt: Date;
}

/** Discriminated union, not `{ ok, error?, refund? }`. Only real states exist. */
export type CreateRefundResult =
  | { outcome: "succeeded"; refund: RefundView; replayed: boolean }
  | { outcome: "pending"; refund: RefundView }              // Stripe outcome unknown
  | { outcome: "order_not_found" }
  | { outcome: "order_not_refundable"; detail: string }
  | { outcome: "exceeds_refundable"; refundableCents: number }
  | { outcome: "idempotency_key_reuse" }
  | { outcome: "declined"; refund: RefundView; code: string };

export class RefundService {
  constructor(
    private readonly db: PrismaClient,
    private readonly stripe: Stripe,
    private readonly now: () => Date,   // injected clock — C9, and it makes the
  ) {}                                  // reconciler testable at its boundary

  async create(input: CreateRefundInput): Promise<CreateRefundResult> {
    const requestHash = hashRequest(input);

    // ---- Phase 1: reserve, atomically. ------------------------------------
    let reserved: Awaited<ReturnType<typeof this.reserve>>;
    try {
      reserved = await this.reserve(input, requestHash);
    } catch (e) {
      if (!isUniqueViolation(e, "Refund_tenantId_idempotencyKey_key")) throw e;
      // Same key seen before. The reservation transaction rolled back cleanly,
      // so there is no orphan row and no double increment.
      return this.replay(input, requestHash);
    }
    if (reserved.kind !== "reserved") return reserved;

    // ---- Phase 2: the external effect, outside the transaction. -----------
    return this.driveToTerminal(input.tenantId, reserved.refund, reserved.paymentIntentId);
  }

  /**
   * One transaction: claim the idempotency key AND reserve the money against the
   * order. Either both happen or neither does. Note there is no read-then-check:
   * the invariant lives in the UPDATE predicate, so two concurrent partial
   * refunds cannot both pass. The CHECK constraint behind it catches any writer
   * that bypasses this method entirely.
   */
  private async reserve(input: CreateRefundInput, requestHash: string) {
    return TenantScope.transaction(this.db, input.tenantId, async (scope) => {
      const order = await scope.tx.order.findFirst({
        where: { id: input.orderId, tenantId: scope.tenantId },
        select: { totalCents: true, refundedCents: true, currency: true, stripePaymentIntentId: true },
      });
      // 404, not 403: a 403 confirms the order exists and leaks tenant membership.
      if (!order) return { kind: "order_not_found" } as const;
      if (!order.stripePaymentIntentId) {
        return { kind: "order_not_refundable", detail: "order has no captured payment" } as const;
      }

      // Claim first: cheapest rejection path, and it rolls back the whole txn.
      const refund = await scope.tx.refund.create({
        data: {
          orderId: input.orderId,
          tenantId: scope.tenantId,
          amountCents: input.amountCents,
          currency: order.currency,          // never client-supplied
          reason: input.reason,
          status: "pending",
          idempotencyKey: input.idempotencyKey,
          requestHash,
          createdByUserId: input.actorId,
        },
      });

      const claimed = await scope.tx.$executeRaw`
        UPDATE "Order"
           SET "refundedCents" = "refundedCents" + ${input.amountCents}::int
         WHERE "id" = ${input.orderId}::uuid
           AND "tenantId" = ${scope.tenantId}::uuid
           AND "refundedCents" + ${input.amountCents}::int <= "totalCents"`;

      if (claimed === 0) {
        // Roll the reservation back rather than leaving a pending refund behind.
        throw new OverRefund(order.totalCents - order.refundedCents);
      }

      return {
        kind: "reserved" as const,
        refund: toView(refund),
        paymentIntentId: order.stripePaymentIntentId,
      };
    }).catch((e) => {
      if (e instanceof OverRefund) {
        return { kind: "exceeds_refundable", refundableCents: e.refundableCents } as const;
      }
      throw e;
    });
  }

  /** Second request under the same key. */
  private async replay(input: CreateRefundInput, requestHash: string): Promise<CreateRefundResult> {
    const existing = await TenantScope.transaction(this.db, input.tenantId, (scope) =>
      scope.tx.refund.findUnique({
        where: { tenantId_idempotencyKey: { tenantId: scope.tenantId, idempotencyKey: input.idempotencyKey } },
        include: { order: { select: { stripePaymentIntentId: true } } },
      }),
    );
    if (!existing) throw new Error("idempotency key vanished between insert and read");

    // A reused key with a different payload is a caller bug, not a no-op.
    if (existing.requestHash !== requestHash) return { outcome: "idempotency_key_reuse" };

    switch (existing.status) {
      case "succeeded": return { outcome: "succeeded", refund: toView(existing), replayed: true };
      case "failed":    return { outcome: "declined", refund: toView(existing), code: existing.failureCode ?? "unknown" };
      case "pending":
        // Self-healing: our Stripe idempotency key is derived from the refund id,
        // so re-driving is safe and converges on the first attempt's outcome.
        return this.driveToTerminal(
          input.tenantId, toView(existing), existing.order.stripePaymentIntentId!,
        );
      default: return assertNever(existing.status);
    }
  }

  /** Calls Stripe, then records the terminal state. Also the reconciler's entry point. */
  async driveToTerminal(
    tenantId: TenantId, refund: RefundView, paymentIntentId: string,
  ): Promise<CreateRefundResult> {
    try {
      const stripeRefund = await this.stripe.refunds.create(
        {
          payment_intent: paymentIntentId,
          amount: refund.amountCents,
          reason: toStripeReason(refund.reason),
          metadata: { refundId: refund.id, tenantId, appReason: refund.reason },
        },
        // Ours, not the client's: stable across retries, unguessable, and it
        // means a client that recycles its key cannot collide inside Stripe.
        { idempotencyKey: `refund:${refund.id}` },
      );
      const settled = await this.settle(tenantId, refund.id, stripeRefund.id);
      return { outcome: "succeeded", refund: settled, replayed: false };
    } catch (e) {
      if (!(e instanceof Stripe.errors.StripeError)) throw e;

      if (isTerminal(e)) {
        const failed = await this.release(tenantId, refund, e.code ?? e.type);
        return { outcome: "declined", refund: failed, code: e.code ?? e.type };
      }
      // Timeout / connection error / 5xx: the refund MAY have happened. Do not
      // release the reservation — an unknown outcome is not a failure. The row
      // stays pending and the reconciler re-drives it against the same key.
      return { outcome: "pending", refund };
    }
  }

  private async settle(tenantId: TenantId, refundId: RefundId, stripeRefundId: string) {
    return TenantScope.transaction(this.db, tenantId, async (scope) => {
      // Guarded transition: only pending -> succeeded, so a racing reconciler
      // cannot apply the effect twice.
      const moved = await scope.tx.refund.updateMany({
        where: { id: refundId, tenantId: scope.tenantId, status: "pending" },
        data: { status: "succeeded", stripeRefundId },
      });
      const row = await scope.tx.refund.findFirstOrThrow({ where: { id: refundId, tenantId: scope.tenantId } });
      if (moved === 0 && row.status !== "succeeded") {
        throw new Error(`illegal transition ${row.status} -> succeeded for refund ${refundId}`);
      }
      return toView(row);
    });
  }

  private async release(tenantId: TenantId, refund: RefundView, code: string) {
    return TenantScope.transaction(this.db, tenantId, async (scope) => {
      const moved = await scope.tx.refund.updateMany({
        where: { id: refund.id, tenantId: scope.tenantId, status: "pending" },
        data: { status: "failed", failureCode: code },
      });
      // Give the money back to the order's refundable budget ONLY if this call
      // is the one that performed the transition.
      if (moved === 1) {
        const released = await scope.tx.$executeRaw`
          UPDATE "Order"
             SET "refundedCents" = "refundedCents" - ${refund.amountCents}::int
           WHERE "id" = ${refund.orderId}::uuid
             AND "tenantId" = ${scope.tenantId}::uuid
             AND "refundedCents" >= ${refund.amountCents}::int`;
        if (released !== 1) throw new Error(`reservation release failed for refund ${refund.id}`);
      }
      return toView(await scope.tx.refund.findFirstOrThrow({
        where: { id: refund.id, tenantId: scope.tenantId },
      }));
    });
  }
}

class OverRefund extends Error {
  constructor(readonly refundableCents: number) { super("exceeds refundable amount"); }
}

/** Binds the key to the payload so a reused key with different values is an error. */
function hashRequest(i: CreateRefundInput): string {
  return createHash("sha256")
    .update(JSON.stringify([i.tenantId, i.orderId, i.amountCents, i.reason]))
    .digest("hex");
}

function isTerminal(e: Stripe.errors.StripeError): boolean {
  // card_error and invalid_request_error mean Stripe decided; the rest mean we
  // do not know. No catch-all: an unrecognised type falls through to "unknown".
  return e.type === "StripeCardError" || e.type === "StripeInvalidRequestError";
}

function isUniqueViolation(e: unknown, constraint: string): boolean {
  return e instanceof Prisma.PrismaClientKnownRequestError
    && e.code === "P2002"
    && JSON.stringify(e.meta ?? {}).includes(constraint.replace(/_key$/, ""));
}

function toView(r: {
  id: string; orderId: string; amountCents: number; currency: string; reason: string;
  status: string; stripeRefundId: string | null; failureCode: string | null; createdAt: Date;
}): RefundView {
  return r as unknown as RefundView; // sole cast: Prisma row -> branded view
}
```

## `src/http/refunds.ts` — parse at the boundary, exhaustive status mapping

```ts
import type { Request, Response } from "express";
import { z } from "zod";
import { config } from "../config";
import { RefundReason } from "../domain/refund";
import { assertNever, Cents, IdempotencyKey, OrderId, TenantId, UserId } from "../domain/ids";
import type { RefundService } from "../services/createRefund";

/**
 * .strict() rejects unknown keys — so a client that sends `tenantId` in the body
 * gets a 400 instead of being quietly ignored. The scoping fields come from the
 * session only, and there is no code path here that reads them from the body.
 */
const RefundBody = z.object({
  orderId: OrderId,
  amountCents: Cents.refine((c) => c <= config.MAX_REFUND_CENTS, {
    message: `amountCents exceeds MAX_REFUND_CENTS (${config.MAX_REFUND_CENTS})`,
  }),
  reason: RefundReason,
}).strict();

const Session = z.object({ userId: UserId, tenantId: TenantId });

export function refundsRouter(service: RefundService) {
  return async function postRefund(req: Request, res: Response) {
    const session = Session.safeParse(req.session);
    if (!session.success) return res.status(401).json({ error: "unauthenticated" });

    const key = IdempotencyKey.safeParse(req.header("Idempotency-Key"));
    if (!key.success) {
      return res.status(400).json({
        error: "Idempotency-Key header is required (16-200 chars). Reuse the same " +
               "key when retrying so the refund cannot be applied twice.",
      });
    }

    const body = RefundBody.safeParse(req.body);
    if (!body.success) return res.status(400).json({ error: body.error.flatten() });

    const result = await service.create({
      tenantId: session.data.tenantId,
      actorId: session.data.userId,
      orderId: body.data.orderId,
      amountCents: body.data.amountCents,
      reason: body.data.reason,
      idempotencyKey: key.data,
    });

    switch (result.outcome) {
      case "succeeded":
        return res.status(result.replayed ? 200 : 201).json(result.refund);
      case "pending":
        return res.status(202)
          .set("Retry-After", "5")
          .json({ ...result.refund, detail: "refund submitted; outcome not yet confirmed" });
      case "order_not_found":
        return res.status(404).json({ error: "order not found" });
      case "order_not_refundable":
        return res.status(422).json({ error: result.detail });
      case "exceeds_refundable":
        return res.status(422).json({ error: "amount exceeds refundable balance", refundableCents: result.refundableCents });
      case "idempotency_key_reuse":
        return res.status(409).json({ error: "Idempotency-Key already used with a different payload" });
      case "declined":
        return res.status(402).json({ error: "refund declined by processor", code: result.code, refund: result.refund });
      default:
        return assertNever(result); // new outcome ⇒ build break, not a 200 with undefined
    }
  };
}
```

`★ Insight ─────────────────────────────────────`
- `202 + pending` is the outcome most refund handlers don't model, and it's the one that costs money. A Stripe timeout is not a failure — releasing the reservation there is how you get a double refund on the client's retry.
- Returning **404** rather than 403 for another tenant's order is deliberate: 403 confirms the resource exists, which leaks tenant membership through an enumeration oracle.
`─────────────────────────────────────────────────`

## `prisma/schema.prisma` — additions

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
  order_canceled
  goodwill
}

model Order {
  id                    String   @id @default(uuid()) @db.Uuid
  tenantId              String   @db.Uuid
  totalCents            Int
  currency              String   @db.Char(3)

  // --- additions ---
  stripePaymentIntentId String?  @unique
  /// Running total of reserved + settled refunds. Maintained only by guarded
  /// UPDATEs; the CHECK below is the backstop for anything that isn't.
  refundedCents         Int      @default(0)
  refunds               Refund[]

  /// Composite keys exist so Refund's FK can carry tenant and currency.
  @@unique([id, tenantId, currency])
  @@index([tenantId])
}

model Refund {
  id              String       @id @default(uuid()) @db.Uuid
  orderId         String       @db.Uuid
  amountCents     Int
  reason          RefundReason
  createdAt       DateTime     @default(now())

  // --- additions ---
  tenantId        String       @db.Uuid
  currency        String       @db.Char(3)
  status          RefundStatus @default(pending)
  idempotencyKey  String       @db.VarChar(200)
  requestHash     String       @db.Char(64)
  stripeRefundId  String?      @unique
  failureCode     String?
  createdByUserId String       @db.Uuid
  updatedAt       DateTime     @updatedAt

  /// Referencing (id, tenantId, currency) makes a cross-tenant refund and a
  /// currency-mismatched refund both unrepresentable at the storage layer.
  order Order @relation(fields: [orderId, tenantId, currency], references: [id, tenantId, currency])

  @@unique([tenantId, idempotencyKey])
  @@index([status, createdAt])   // reconciler scan
  @@index([orderId])
}
```

## `prisma/migrations/20260822_refunds/migration.sql`

Expand-only — no destructive DDL, so it is safe to deploy ahead of the code (M7).

```sql
BEGIN;

-- 1. Enums. Converting Refund.reason fails loudly if any existing value is
--    outside the set, which is the correct behaviour for a payments table.
CREATE TYPE "RefundStatus" AS ENUM ('pending', 'succeeded', 'failed');
CREATE TYPE "RefundReason" AS ENUM (
  'duplicate', 'fraudulent', 'requested_by_customer', 'order_canceled', 'goodwill'
);

-- 2. Order: reservation counter + Stripe linkage.
ALTER TABLE "Order"
  ADD COLUMN "stripePaymentIntentId" TEXT,
  ADD COLUMN "refundedCents" INTEGER NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX "Order_stripePaymentIntentId_key"
  ON "Order" ("stripePaymentIntentId") WHERE "stripePaymentIntentId" IS NOT NULL;

-- The over-refund control. Holds against this service, other services,
-- migrations, and anyone with a psql shell.
ALTER TABLE "Order"
  ADD CONSTRAINT "Order_refundedCents_within_total"
  CHECK ("refundedCents" >= 0 AND "refundedCents" <= "totalCents"),
  ADD CONSTRAINT "Order_totalCents_nonnegative" CHECK ("totalCents" >= 0),
  ADD CONSTRAINT "Order_currency_iso4217" CHECK ("currency" ~ '^[A-Z]{3}$');

ALTER TABLE "Order"
  ADD CONSTRAINT "Order_id_tenantId_currency_key" UNIQUE ("id", "tenantId", "currency");

-- 3. Refund: expand, backfill, then constrain.
ALTER TABLE "Refund"
  ADD COLUMN "tenantId" UUID,
  ADD COLUMN "currency" CHAR(3),
  ADD COLUMN "status" "RefundStatus" NOT NULL DEFAULT 'pending',
  ADD COLUMN "idempotencyKey" VARCHAR(200),
  ADD COLUMN "requestHash" CHAR(64),
  ADD COLUMN "stripeRefundId" TEXT,
  ADD COLUMN "failureCode" TEXT,
  ADD COLUMN "createdByUserId" UUID,
  ADD COLUMN "updatedAt" TIMESTAMPTZ NOT NULL DEFAULT now();

UPDATE "Refund" r
   SET "tenantId" = o."tenantId",
       "currency" = o."currency",
       "status"   = 'succeeded',
       "idempotencyKey" = 'legacy:' || r."id"::text,
       "requestHash"    = encode(sha256(('legacy:' || r."id"::text)::bytea), 'hex')
  FROM "Order" o
 WHERE o."id" = r."orderId";

-- Pre-existing rows have no known actor; adopt the tenant's system user.
UPDATE "Refund" SET "createdByUserId" = '00000000-0000-0000-0000-000000000000'
 WHERE "createdByUserId" IS NULL;

ALTER TABLE "Refund"
  ALTER COLUMN "tenantId"        SET NOT NULL,
  ALTER COLUMN "currency"        SET NOT NULL,
  ALTER COLUMN "idempotencyKey"  SET NOT NULL,
  ALTER COLUMN "requestHash"     SET NOT NULL,
  ALTER COLUMN "createdByUserId" SET NOT NULL,
  ALTER COLUMN "reason" TYPE "RefundReason" USING "reason"::"RefundReason";

-- Reconcile the counter with history before the CHECK starts enforcing it.
UPDATE "Order" o
   SET "refundedCents" = COALESCE(
     (SELECT SUM(r."amountCents") FROM "Refund" r
       WHERE r."orderId" = o."id" AND r."status" <> 'failed'), 0);

ALTER TABLE "Refund"
  ADD CONSTRAINT "Refund_amount_positive" CHECK ("amountCents" > 0),
  -- A succeeded refund without a Stripe id is unrepresentable, and so is a
  -- failed one without a cause.
  ADD CONSTRAINT "Refund_succeeded_has_stripe_id"
    CHECK ("status" <> 'succeeded' OR "stripeRefundId" IS NOT NULL),
  ADD CONSTRAINT "Refund_failed_has_code"
    CHECK ("status" <> 'failed' OR "failureCode" IS NOT NULL);

-- One refund per (tenant, idempotency key). This is the device; the
-- application-level check is only an optimisation in front of it.
CREATE UNIQUE INDEX "Refund_tenantId_idempotencyKey_key"
  ON "Refund" ("tenantId", "idempotencyKey");
CREATE UNIQUE INDEX "Refund_stripeRefundId_key"
  ON "Refund" ("stripeRefundId") WHERE "stripeRefundId" IS NOT NULL;
CREATE INDEX "Refund_status_createdAt_idx" ON "Refund" ("status", "createdAt");

-- Cross-tenant / cross-currency refunds become storage-level impossible.
ALTER TABLE "Refund"
  ADD CONSTRAINT "Refund_order_fkey"
  FOREIGN KEY ("orderId", "tenantId", "currency")
  REFERENCES "Order" ("id", "tenantId", "currency")
  ON UPDATE CASCADE ON DELETE RESTRICT;

-- 4. Row-level security: the only device that covers code you did not write.
ALTER TABLE "Order"  ENABLE ROW LEVEL SECURITY;
ALTER TABLE "Order"  FORCE  ROW LEVEL SECURITY;
ALTER TABLE "Refund" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "Refund" FORCE  ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON "Order"
  USING ("tenantId" = current_setting('app.tenant_id', true)::uuid);
CREATE POLICY tenant_isolation ON "Refund"
  USING ("tenantId" = current_setting('app.tenant_id', true)::uuid);

COMMIT;
```

> **Contract migration, later deploy:** once every order has a
> `stripePaymentIntentId`, `ALTER TABLE "Order" ALTER COLUMN "stripePaymentIntentId" SET NOT NULL`.
> Until then the handler's `order_not_refundable` branch is the only thing enforcing it — a
> Warning, not a Control, and it's the weakest link in this design.

## `src/jobs/reconcileRefunds.ts` — the Detection rung behind it

```ts
/** Any pending refund older than the threshold is re-driven against the same
 *  Stripe idempotency key, converging on the first attempt's real outcome.
 *  Without this, a Stripe timeout freezes an order's refundable budget forever. */
export async function reconcilePendingRefunds(db: PrismaClient, service: RefundService, now: () => Date) {
  const stale = await db.refund.findMany({
    where: { status: "pending", createdAt: { lt: new Date(now().getTime() - config.REFUND_RECONCILE_AFTER_MS) } },
    include: { order: { select: { stripePaymentIntentId: true } } },
    take: 200,   // capped: a backlog must not become an unbounded job
  });
  for (const r of stale) {
    if (!r.order.stripePaymentIntentId) continue;
    await service.driveToTerminal(r.tenantId as TenantId, toView(r), r.order.stripePaymentIntentId);
  }
}
```

## `src/services/createRefund.test.ts` — the checks that prove the devices

```ts
describe("POST /refunds", () => {
  it("refuses tenant A a refund on tenant B's order with 404, not 403", async () => {
    const res = await post("/refunds", { orderId: tenantB.order.id, amountCents: 100, reason: "duplicate" },
      { session: tenantA.session, key: freshKey() });
    expect(res.status).toBe(404);
    expect(await countRefunds(tenantB.order.id)).toBe(0);
  });

  it("applies a retried request exactly once", async () => {
    const key = freshKey();
    const a = await post("/refunds", body, { session, key });
    const b = await post("/refunds", body, { session, key });
    expect(a.status).toBe(201); expect(b.status).toBe(200);
    expect(b.body.id).toBe(a.body.id);
    expect(stripe.refunds.create).toHaveBeenCalledTimes(1);
  });

  it("rejects a reused key carrying a different amount", async () => {
    const key = freshKey();
    await post("/refunds", { ...body, amountCents: 500 }, { session, key });
    const res = await post("/refunds", { ...body, amountCents: 900 }, { session, key });
    expect(res.status).toBe(409);
  });

  it("lets only one of two concurrent partials past the remaining balance", async () => {
    // order.totalCents = 1000, already refunded 600 → 400 remaining
    const [x, y] = await Promise.all([
      post("/refunds", { ...body, amountCents: 400 }, { session, key: freshKey() }),
      post("/refunds", { ...body, amountCents: 400 }, { session, key: freshKey() }),
    ]);
    expect([x.status, y.status].sort()).toEqual([201, 422]);
    expect((await order()).refundedCents).toBe(1000);
  });

  it("keeps the reservation when Stripe times out", async () => {
    stripe.refunds.create.mockRejectedValueOnce(new Stripe.errors.StripeConnectionError({ message: "timeout" }));
    const res = await post("/refunds", body, { session, key: freshKey() });
    expect(res.status).toBe(202);
    expect((await order()).refundedCents).toBe(body.amountCents); // NOT released
  });

  it("releases the reservation when Stripe declines", async () => {
    stripe.refunds.create.mockRejectedValueOnce(
      new Stripe.errors.StripeInvalidRequestError({ message: "already refunded", code: "charge_already_refunded" }));
    const res = await post("/refunds", body, { session, key: freshKey() });
    expect(res.status).toBe(402);
    expect((await order()).refundedCents).toBe(0);
  });
});
```

---

## What this makes impossible, and at which rung

| Misuse | Device | Rung |
|---|---|---|
| Swapping order/tenant/user ids | Branded types | **Control** (compile) |
| Cross-tenant refund | `TenantScope` + composite FK + RLS | **Control** ×3, independent |
| Client-supplied `tenantId` | Session-only source + `.strict()` body | **Control** |
| Double refund on retry | Required `Idempotency-Key` + `UNIQUE(tenantId, key)` + Stripe key from refund id | **Control** |
| Same key, different payload | `requestHash` bound to the key | **Control** |
| Over-refund, incl. concurrent partials | Guarded `UPDATE … WHERE refunded + amt <= total` + `CHECK` | **Control** |
| Money out with no row | Reserve → call → settle, with pending as the durable middle state | **Control** |
| Currency mismatch | Currency in the composite FK | **Control** |
| Unmapped new reason | `assertNever` in `toStripeReason` | **Control** (build break) |
| Unhandled new outcome | `assertNever` in the handler switch | **Control** |
| Missing `STRIPE_SECRET_KEY` | Boot-time parse + `exit(1)` | **Control** (fails deploy) |
| Stuck `pending` after a timeout | Reconciler job | **Detection** |

**Left possible on purpose.** Three things:

1. **`stripePaymentIntentId` is nullable**, so "refund an order that was never captured" is caught by the handler (Warning) rather than the schema. Control needs a backfill first; the contract migration is noted in the SQL.
2. **RLS depends on middleware.** `TenantScope` is the only path to a connection today, but nothing stops a future `prisma.refund.findMany()` in a handler — close that with an ESLint `no-restricted-imports` on `@prisma/client` outside `src/db/`. That's the missing device.
3. **No approval gate on large refunds.** `MAX_REFUND_CENTS` is a flat ceiling; a refund near an order's full total from a low-privilege actor is currently allowed. If your risk model wants a second pair of eyes above some threshold, that's a state-machine addition (`pending_approval`) rather than a check — tell me the threshold and who can approve and I'll add the transition.