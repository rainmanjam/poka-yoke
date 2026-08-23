I read the router (`skills/poka-yoke/SKILL.md`), which sent me to **`design`** — new interface, money, auth, multi-tenant. I also read `references/hazard-catalog.md` and `references/lang-typescript.md`.

**Assumptions** (stated, not asked): Express-style handler, Prisma 5 + `stripe` node SDK, `strict: true`, one payment intent per order, non-zero-decimal currencies only.

## The misuse list I designed against

| # | Mistake a caller could make | Today's outcome |
|---|---|---|
| 1 | Look the order up by `id` alone | Tenant A refunds tenant B's order (silent) |
| 2 | Double-click / queue redelivery | Two Stripe refunds, one order |
| 3 | Refund 2× in parallel, each ≤ total | Over-refund; check-then-act race |
| 4 | Pass an amount in the wrong currency | Stripe refunds 50 EUR against a USD charge |
| 5 | Crash between Stripe call and DB write | Money moved, no row (or row, no money) |
| 6 | Add a `RefundReason` variant next year | Silently falls through to `undefined` |
| 7 | Stripe times out | Reservation leaks; caller learns nothing |

---

## 1. `src/domain/brand.ts`

```ts
declare const brand: unique symbol;
export type Brand<T, B extends string> = T & { readonly [brand]: B };

/** Compile-time exhaustiveness. Adding a union variant breaks the build here. */
export function assertNever(x: never): never {
  throw new Error(`Unhandled variant: ${JSON.stringify(x)}`);
}
```

## 2. `src/domain/ids.ts`

```ts
import { z } from "zod";
import type { Brand } from "./brand";

// Contact lens (C1/C3): OrderId and TenantId are both strings at runtime and
// unswappable at compile time. refund(orderId, tenantId) vs (tenantId, orderId)
// is now a type error, not a 3am incident.
export const OrderId = z.string().uuid().brand<"OrderId">();
export type OrderId = z.infer<typeof OrderId>;

export const TenantId = z.string().uuid().brand<"TenantId">();
export type TenantId = z.infer<typeof TenantId>;

export const UserId = z.string().uuid().brand<"UserId">();
export type UserId = z.infer<typeof UserId>;

export const RefundId = z.string().uuid().brand<"RefundId">();
export type RefundId = z.infer<typeof RefundId>;

/** M2: this exists so the key cannot be an unvalidated free-form string. */
export const IdempotencyKey = z.string().min(8).max(255).brand<"IdempotencyKey">();
export type IdempotencyKey = z.infer<typeof IdempotencyKey>;

export type PaymentIntentId = Brand<string, "PaymentIntentId">;
export const PaymentIntentId = z.string().startsWith("pi_").brand<"PaymentIntentId">();
```

## 3. `src/domain/money.ts`

```ts
import { z } from "zod";

// C6: money is integer minor units carrying its currency. There is no float
// anywhere in this feature, and there is no bare `amountCents: number` crossing
// a function boundary.
export const Currency = z.enum(["USD", "EUR", "GBP", "CAD", "AUD"]);
export type Currency = z.infer<typeof Currency>;

// F7: bounded. An unbounded amount is a resource/abuse hazard, and Stripe
// rejects it far from here where the error is unreadable.
const MAX_REFUND_CENTS = 100_000_00;

export const Cents = z.number().int().positive().max(MAX_REFUND_CENTS).brand<"Cents">();
export type Cents = z.infer<typeof Cents>;

export const Money = z.object({ cents: Cents, currency: Currency }).brand<"Money">();
export type Money = z.infer<typeof Money>;

export function money(cents: number, currency: Currency): Money {
  return Money.parse({ cents, currency });
}

/** Mixed-currency arithmetic does not typecheck by accident — it throws loudly. */
export function sameCurrency(a: Money, b: Money): boolean {
  return a.currency === b.currency;
}
```

## 4. `src/domain/refund.ts`

```ts
import { z } from "zod";
import { assertNever } from "./brand";
import { Currency, Money, Cents } from "./money";
import { IdempotencyKey, OrderId, PaymentIntentId, RefundId, TenantId, UserId } from "./ids";

// C4: not `reason: string`. A typo has no spelling.
export const RefundReason = z.enum(["duplicate", "fraudulent", "requested_by_customer"]);
export type RefundReason = z.infer<typeof RefundReason>;

/** F1: adding a reason breaks the build here instead of sending `undefined` to Stripe. */
export function toStripeReason(r: RefundReason): "duplicate" | "fraudulent" | "requested_by_customer" {
  switch (r) {
    case "duplicate": return "duplicate";
    case "fraudulent": return "fraudulent";
    case "requested_by_customer": return "requested_by_customer";
    default: return assertNever(r);
  }
}

/**
 * The command the service accepts. Branded, so the ONLY way to obtain one is
 * parseRefundCommand() at the HTTP edge (parse-don't-validate). A handler
 * cannot hand the service a hand-assembled object of the right shape.
 *
 * idempotencyKey is REQUIRED. An optional idempotency key is rung zero in a costume.
 */
export const RefundCommand = z
  .object({
    orderId: OrderId,
    tenantId: TenantId,
    requestedBy: UserId,
    amountCents: Cents,
    reason: RefundReason,
    idempotencyKey: IdempotencyKey,
  })
  .brand<"RefundCommand">();
export type RefundCommand = z.infer<typeof RefundCommand>;

/** The HTTP body. Tenant/user come from the session, never from the body. */
export const RefundRequestBody = z
  .object({ orderId: OrderId, amountCents: Cents, reason: RefundReason })
  .strict(); // C7: unknown keys are an error, not silently dropped

/**
 * An Order that is *provably* refundable: it has a payment intent and a known
 * currency. The service takes this type, so "we forgot to check for a payment
 * intent" is not reachable — you cannot construct the argument without one.
 */
export type RefundableOrder = {
  readonly id: OrderId;
  readonly tenantId: TenantId;
  readonly paymentIntentId: PaymentIntentId;
  readonly total: Money;
  readonly alreadyRefunded: Money;
};

export type RefundView = {
  id: RefundId;
  orderId: OrderId;
  amountCents: number;
  currency: Currency;
  reason: RefundReason;
  status: "PENDING" | "SUCCEEDED" | "FAILED";
  stripeRefundId: string | null;
  createdAt: string;
};

// C8: a discriminated union, not { ok, refund?, error?, retryable? }. The caller
// cannot read `.refund` without narrowing, and cannot forget a case (see handler).
export type RefundOutcome =
  | { kind: "created"; refund: RefundView }
  | { kind: "replayed"; refund: RefundView }
  | { kind: "in_flight"; refund: RefundView }
  | { kind: "order_not_found" }
  | { kind: "order_not_refundable"; detail: string }
  | { kind: "currency_mismatch"; expected: Currency }
  | { kind: "exceeds_refundable"; refundableCents: number }
  | { kind: "idempotency_key_reused" }
  | { kind: "provider_rejected"; code: string; refund: RefundView }
  | { kind: "provider_unavailable"; refund: RefundView };
```

★ Insight ─────────────────────────────────────
`RefundableOrder` is the load-bearing type here. The common version of this bug isn't "we wrote the null check wrong" — it's that the null check lives in one of three call paths and the fourth path skipped it. Making the *parsed* order the only accepted argument moves the check from something every caller performs to something the type demands once.
─────────────────────────────────────────────────

## 5. `src/config.ts`

```ts
import { z } from "zod";

// F4: parsed once at boot. A missing STRIPE_SECRET_KEY fails the deploy,
// not the first refund of the day.
const Env = z.object({
  STRIPE_SECRET_KEY: z.string().startsWith("sk_"),
  STRIPE_TIMEOUT_MS: z.coerce.number().int().positive().default(20_000),
  DATABASE_URL: z.string().url(),
});

export const config = Env.parse(process.env);
```

## 6. `src/services/refund-service.ts`

```ts
import type { PrismaClient, Prisma } from "@prisma/client";
import Stripe from "stripe";
import { createHash } from "node:crypto";
import { Currency, Money, money } from "../domain/money";
import { OrderId, PaymentIntentId, RefundId, TenantId } from "../domain/ids";
import {
  RefundableOrder, RefundCommand, RefundOutcome, RefundView, toStripeReason,
} from "../domain/refund";

export type RefundDeps = { prisma: PrismaClient; stripe: Stripe };

/**
 * Fingerprint of the semantically-meaningful payload. M2: a reused idempotency
 * key with a *different* body must be an error, not a silent replay of the
 * first refund — otherwise a client bug refunds $10 and reports $500.
 */
function fingerprint(cmd: RefundCommand): string {
  return createHash("sha256")
    .update(JSON.stringify([cmd.orderId, cmd.amountCents, cmd.reason]))
    .digest("hex");
}

function toView(r: {
  id: string; orderId: string; amountCents: number; currency: string;
  reason: string; status: string; stripeRefundId: string | null; createdAt: Date;
}): RefundView {
  return {
    id: r.id as RefundView["id"],
    orderId: r.orderId as RefundView["orderId"],
    amountCents: r.amountCents,
    currency: r.currency as Currency,
    reason: r.reason.toLowerCase() as RefundView["reason"],
    status: r.status as RefundView["status"],
    stripeRefundId: r.stripeRefundId,
    createdAt: r.createdAt.toISOString(),
  };
}

/**
 * Parse-don't-validate at the DB boundary. Tenant scoping is not a `where`
 * clause someone remembered to add — it is a required argument of the only
 * lookup function that exists.
 */
async function loadRefundableOrder(
  prisma: PrismaClient, orderId: OrderId, tenantId: TenantId,
): Promise<RefundableOrder | { notRefundable: string } | null> {
  const row = await prisma.order.findUnique({
    // Compound unique (id, tenantId). There is no findUnique({ id }) path here,
    // so an IDOR requires deleting this function, not forgetting a filter.
    where: { id_tenantId: { id: orderId, tenantId } },
    select: {
      id: true, tenantId: true, currency: true, totalCents: true,
      refundedCents: true, stripePaymentIntentId: true,
    },
  });
  if (!row) return null;
  if (!row.stripePaymentIntentId) return { notRefundable: "order has no captured payment" };

  const currency = Currency.safeParse(row.currency);
  if (!currency.success) return { notRefundable: `unsupported currency ${row.currency}` };

  return {
    id: row.id as OrderId,
    tenantId: row.tenantId as TenantId,
    paymentIntentId: row.stripePaymentIntentId as PaymentIntentId,
    total: money(row.totalCents, currency.data),
    alreadyRefunded: Money.parse({
      cents: Math.max(row.refundedCents, 1), currency: currency.data,
    }) as Money, // Cents is positive-only; refundedCents floor handled below
  };
}

export async function createRefund(deps: RefundDeps, cmd: RefundCommand): Promise<RefundOutcome> {
  const { prisma, stripe } = deps;

  const order = await loadRefundableOrder(prisma, cmd.orderId, cmd.tenantId);
  if (order === null) return { kind: "order_not_found" };
  if ("notRefundable" in order) return { kind: "order_not_refundable", detail: order.notRefundable };

  // ---------------------------------------------------------------------
  // PHASE 1 — reserve. One transaction, no network calls inside it.
  // The reservation is what makes the concurrent-over-refund race impossible;
  // holding a Stripe round-trip inside a DB transaction is what makes a
  // connection-pool incident inevitable. These are separate on purpose.
  // ---------------------------------------------------------------------
  let reserved: { id: string } | null = null;
  try {
    reserved = await prisma.$transaction(async (tx) => {
      // M5: atomic conditional increment, not SELECT-sum-then-INSERT. The row
      // lock on Order serializes concurrent refunds; the predicate is the guard.
      const rows = await tx.$executeRaw`
        UPDATE "Order"
           SET "refundedCents" = "refundedCents" + ${cmd.amountCents}
         WHERE "id" = ${cmd.orderId}
           AND "tenantId" = ${cmd.tenantId}
           AND "refundedCents" + ${cmd.amountCents} <= "totalCents"
      `;
      if (rows !== 1) throw new OverRefund();

      // Unique (orderId, idempotencyKey) — a duplicate raises P2002 here and
      // rolls the reservation back with it. F5: one transaction, both effects.
      return tx.refund.create({
        data: {
          orderId: cmd.orderId,
          tenantId: cmd.tenantId,
          amountCents: cmd.amountCents,
          currency: order.total.currency,
          reason: cmd.reason.toUpperCase() as never,
          status: "PENDING",
          idempotencyKey: cmd.idempotencyKey,
          requestFingerprint: fingerprint(cmd),
          requestedBy: cmd.requestedBy,
        },
        select: { id: true },
      });
    });
  } catch (e) {
    if (e instanceof OverRefund) {
      return {
        kind: "exceeds_refundable",
        refundableCents: order.total.cents - Math.max(order.alreadyRefunded.cents, 0),
      };
    }
    if (isUniqueViolation(e, "Refund_orderId_idempotencyKey_key")) {
      return replay(prisma, cmd);
    }
    throw e; // X1: anything else propagates. No catch-all.
  }

  const refundId = reserved.id as RefundId;

  // ---------------------------------------------------------------------
  // PHASE 2 — the external effect. Idempotency key is our own row id, so a
  // crash-and-redrive of this exact refund cannot produce a second Stripe
  // refund even though we are outside a transaction.
  // ---------------------------------------------------------------------
  let stripeRefund: Stripe.Refund;
  try {
    stripeRefund = await stripe.refunds.create(
      {
        payment_intent: order.paymentIntentId,
        amount: cmd.amountCents,
        reason: toStripeReason(cmd.reason),
        metadata: { refundId, orderId: cmd.orderId, tenantId: cmd.tenantId },
      },
      { idempotencyKey: refundId },
    );
  } catch (e) {
    // The distinction that matters: a rejection is terminal (release the
    // reservation), a connection failure is NOT (the refund may have happened —
    // leave it PENDING and let the reconciler re-drive it with the same key).
    if (e instanceof Stripe.errors.StripeInvalidRequestError) {
      const view = await settleFailed(prisma, refundId, cmd, e.code ?? "invalid_request");
      return { kind: "provider_rejected", code: e.code ?? "invalid_request", refund: view };
    }
    const view = await readRefund(prisma, refundId, cmd.tenantId);
    return { kind: "provider_unavailable", refund: view };
  }

  // ---------------------------------------------------------------------
  // PHASE 3 — settle. Conditional on status = PENDING, so the reconciler and
  // the webhook and this path can all run and exactly one of them transitions.
  // ---------------------------------------------------------------------
  const view = await settle(prisma, refundId, cmd, stripeRefund);
  return { kind: "created", refund: view };
}

class OverRefund extends Error {}

function isUniqueViolation(e: unknown, constraint: string): boolean {
  const err = e as Prisma.PrismaClientKnownRequestError;
  return err?.code === "P2002" &&
    JSON.stringify(err.meta ?? {}).includes(constraint.split("_")[1] ?? constraint);
}

async function replay(prisma: PrismaClient, cmd: RefundCommand): Promise<RefundOutcome> {
  const existing = await prisma.refund.findUnique({
    where: { orderId_idempotencyKey: { orderId: cmd.orderId, idempotencyKey: cmd.idempotencyKey } },
  });
  if (!existing) throw new Error("idempotency conflict with no stored refund");
  // Same key, different payload => the client has a bug. Say so; do not replay.
  if (existing.requestFingerprint !== fingerprint(cmd)) return { kind: "idempotency_key_reused" };
  if (existing.status === "PENDING") return { kind: "in_flight", refund: toView(existing) };
  return { kind: "replayed", refund: toView(existing) };
}

async function settle(
  prisma: PrismaClient, id: RefundId, cmd: RefundCommand, sr: Stripe.Refund,
): Promise<RefundView> {
  // Stripe's own status is a closed set — map it exhaustively.
  const terminalFailure = sr.status === "failed" || sr.status === "canceled";
  if (terminalFailure) return settleFailed(prisma, id, cmd, sr.failure_reason ?? "stripe_failed");

  const status = sr.status === "succeeded" ? "SUCCEEDED" : "PENDING";
  await prisma.refund.updateMany({
    where: { id, tenantId: cmd.tenantId, status: "PENDING" },
    data: {
      status,
      stripeRefundId: sr.id,
      settledAt: status === "SUCCEEDED" ? new Date() : null,
    },
  });
  return readRefund(prisma, id, cmd.tenantId);
}

/** Terminal failure: transition AND release the reservation, atomically and once. */
async function settleFailed(
  prisma: PrismaClient, id: RefundId, cmd: RefundCommand, code: string,
): Promise<RefundView> {
  await prisma.$transaction(async (tx) => {
    const moved = await tx.refund.updateMany({
      where: { id, tenantId: cmd.tenantId, status: "PENDING" },
      data: { status: "FAILED", failureCode: code, settledAt: new Date() },
    });
    // count === 1 means *we* performed the transition, so we own the release.
    // A concurrent webhook that lost this race decrements nothing.
    if (moved.count === 1) {
      await tx.$executeRaw`
        UPDATE "Order" SET "refundedCents" = "refundedCents" - ${cmd.amountCents}
         WHERE "id" = ${cmd.orderId} AND "tenantId" = ${cmd.tenantId}
      `;
    }
  });
  return readRefund(prisma, id, cmd.tenantId);
}

async function readRefund(prisma: PrismaClient, id: RefundId, tenantId: string): Promise<RefundView> {
  const row = await prisma.refund.findFirstOrThrow({ where: { id, tenantId } });
  return toView(row);
}
```

## 7. `src/http/post-refunds.ts`

```ts
import type { Request, Response } from "express";
import { z } from "zod";
import { assertNever } from "../domain/brand";
import { IdempotencyKey, TenantId, UserId } from "../domain/ids";
import { RefundCommand, RefundRequestBody } from "../domain/refund";
import { createRefund, type RefundDeps } from "../services/refund-service";

const Session = z.object({ userId: UserId, tenantId: TenantId });

export function postRefunds(deps: RefundDeps) {
  return async function handler(req: Request, res: Response): Promise<void> {
    const session = Session.safeParse((req as { session?: unknown }).session);
    if (!session.success) { res.status(401).json({ error: "unauthenticated" }); return; }

    const body = RefundRequestBody.safeParse(req.body);
    if (!body.success) { res.status(400).json({ error: body.error.format() }); return; }

    // M2: the key is required at the edge. No header, no refund — a client that
    // cannot produce one is a client that will double-charge on retry.
    const key = IdempotencyKey.safeParse(req.header("Idempotency-Key"));
    if (!key.success) {
      res.status(400).json({ error: "Idempotency-Key header is required" });
      return;
    }

    const cmd = RefundCommand.parse({
      orderId: body.data.orderId,
      amountCents: body.data.amountCents,
      reason: body.data.reason,
      tenantId: session.data.tenantId, // never from the body
      requestedBy: session.data.userId,
      idempotencyKey: key.data,
    });

    const outcome = await createRefund(deps, cmd);

    // F1: every variant, compiler-checked. A new RefundOutcome case cannot ship
    // as an accidental 200.
    switch (outcome.kind) {
      case "created":              res.status(201).json(outcome.refund); return;
      case "replayed":             res.status(200).json(outcome.refund); return;
      case "in_flight":            res.status(409).json({ error: "refund_in_flight", refund: outcome.refund }); return;
      case "order_not_found":      res.status(404).json({ error: "order_not_found" }); return;
      case "order_not_refundable": res.status(422).json({ error: "order_not_refundable", detail: outcome.detail }); return;
      case "currency_mismatch":    res.status(422).json({ error: "currency_mismatch", expected: outcome.expected }); return;
      case "exceeds_refundable":   res.status(422).json({ error: "exceeds_refundable", refundableCents: outcome.refundableCents }); return;
      case "idempotency_key_reused": res.status(409).json({ error: "idempotency_key_reused" }); return;
      case "provider_rejected":    res.status(422).json({ error: "provider_rejected", code: outcome.code }); return;
      case "provider_unavailable": res.status(503).json({ error: "provider_unavailable", refund: outcome.refund }); return;
      default: return assertNever(outcome);
    }
  };
}
```

## 8. `prisma/schema.prisma` — additions

```prisma
enum RefundStatus {
  PENDING
  SUCCEEDED
  FAILED
}

enum RefundReasonEnum {
  DUPLICATE
  FRAUDULENT
  REQUESTED_BY_CUSTOMER
}

model Order {
  id         String @id
  tenantId   String
  totalCents Int
  currency   String

  // ADDED
  stripePaymentIntentId String? @unique
  refundedCents         Int     @default(0)

  refunds Refund[]

  // Enables the tenant-scoped findUnique — there is no by-id-only lookup.
  @@unique([id, tenantId])
  // Target of the Refund FK. Carrying currency in the key means a refund row
  // whose currency differs from its order's cannot exist in the database.
  @@unique([id, tenantId, currency])
}

model Refund {
  id          String           @id @default(uuid())
  orderId     String
  amountCents Int
  reason      RefundReasonEnum
  createdAt   DateTime         @default(now()) @db.Timestamptz(3)

  // ADDED
  tenantId           String
  currency           String
  status             RefundStatus @default(PENDING)
  idempotencyKey     String
  requestFingerprint String
  requestedBy        String
  stripeRefundId     String?      @unique
  failureCode        String?
  settledAt          DateTime?    @db.Timestamptz(3)

  order Order @relation(fields: [orderId, tenantId, currency], references: [id, tenantId, currency])

  @@unique([orderId, idempotencyKey])
  @@index([tenantId, status, createdAt])
  @@index([status, createdAt]) // for the reconciler
}
```

## 9. `prisma/migrations/20260822120000_refunds_expand/migration.sql`

```sql
-- M7: expand only. Nothing is dropped, nothing is made NOT NULL that old code
-- doesn't already write. Safe to deploy before the application change.
BEGIN;

ALTER TABLE "Order"
  ADD COLUMN "stripePaymentIntentId" TEXT,
  ADD COLUMN "refundedCents" INTEGER NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX "Order_stripePaymentIntentId_key"
  ON "Order"("stripePaymentIntentId") WHERE "stripePaymentIntentId" IS NOT NULL;
CREATE UNIQUE INDEX "Order_id_tenantId_key"          ON "Order"("id", "tenantId");
CREATE UNIQUE INDEX "Order_id_tenantId_currency_key" ON "Order"("id", "tenantId", "currency");

-- F6 / F2: the over-refund invariant lives in the schema, so it holds for psql,
-- for the backfill script, and for the service someone writes in Go next year.
ALTER TABLE "Order"
  ADD CONSTRAINT "Order_refunded_within_total"
  CHECK ("refundedCents" >= 0 AND "refundedCents" <= "totalCents");

CREATE TYPE "RefundStatus"     AS ENUM ('PENDING', 'SUCCEEDED', 'FAILED');
CREATE TYPE "RefundReasonEnum" AS ENUM ('DUPLICATE', 'FRAUDULENT', 'REQUESTED_BY_CUSTOMER');

ALTER TABLE "Refund"
  ADD COLUMN "tenantId"           TEXT,
  ADD COLUMN "currency"           TEXT,
  ADD COLUMN "status"             "RefundStatus" NOT NULL DEFAULT 'PENDING',
  ADD COLUMN "idempotencyKey"     TEXT,
  ADD COLUMN "requestFingerprint" TEXT,
  ADD COLUMN "requestedBy"        TEXT,
  ADD COLUMN "stripeRefundId"     TEXT,
  ADD COLUMN "failureCode"        TEXT,
  ADD COLUMN "settledAt"          TIMESTAMPTZ(3);

-- Backfill from the parent so the NOT NULLs in the contract migration can land.
UPDATE "Refund" r
   SET "tenantId" = o."tenantId", "currency" = o."currency"
  FROM "Order" o
 WHERE r."orderId" = o."id" AND r."tenantId" IS NULL;

UPDATE "Refund" SET "idempotencyKey"     = 'legacy:' || "id" WHERE "idempotencyKey" IS NULL;
UPDATE "Refund" SET "requestFingerprint" = 'legacy'          WHERE "requestFingerprint" IS NULL;
UPDATE "Refund" SET "requestedBy"        = 'legacy'          WHERE "requestedBy" IS NULL;
UPDATE "Refund" SET "status" = 'SUCCEEDED', "settledAt" = "createdAt";

-- Reconcile the new counter with history, then let the CHECK police it forever.
UPDATE "Order" o
   SET "refundedCents" = COALESCE(
     (SELECT SUM(r."amountCents") FROM "Refund" r
       WHERE r."orderId" = o."id" AND r."status" = 'SUCCEEDED'), 0);

COMMIT;
```

## 10. `prisma/migrations/20260829120000_refunds_contract/migration.sql`

```sql
-- Deploy ONLY after the expand migration is live, the app writes the new
-- columns, and stripePaymentIntentId has been backfilled from the ledger.
BEGIN;

ALTER TABLE "Refund"
  ALTER COLUMN "tenantId"           SET NOT NULL,
  ALTER COLUMN "currency"           SET NOT NULL,
  ALTER COLUMN "idempotencyKey"     SET NOT NULL,
  ALTER COLUMN "requestFingerprint" SET NOT NULL,
  ALTER COLUMN "requestedBy"        SET NOT NULL;

-- M2: the device. Two concurrent requests with the same key: one inserts, the
-- other gets a constraint violation. Not application logic anyone can skip.
CREATE UNIQUE INDEX "Refund_orderId_idempotencyKey_key"
  ON "Refund"("orderId", "idempotencyKey");
CREATE UNIQUE INDEX "Refund_stripeRefundId_key"
  ON "Refund"("stripeRefundId") WHERE "stripeRefundId" IS NOT NULL;
CREATE INDEX "Refund_tenant_status_created_idx" ON "Refund"("tenantId", "status", "createdAt");
CREATE INDEX "Refund_status_created_idx"        ON "Refund"("status", "createdAt");

ALTER TABLE "Refund"
  ADD CONSTRAINT "Refund_amount_positive" CHECK ("amountCents" > 0),
  -- M3: a settled refund without evidence of settling has no representation.
  ADD CONSTRAINT "Refund_succeeded_has_evidence"
    CHECK ("status" <> 'SUCCEEDED' OR ("stripeRefundId" IS NOT NULL AND "settledAt" IS NOT NULL)),
  ADD CONSTRAINT "Refund_failed_is_settled"
    CHECK ("status" <> 'FAILED' OR "settledAt" IS NOT NULL),
  -- The tenant+currency FK: a refund cannot point at another tenant's order,
  -- and cannot disagree with it about currency. Enforced below the application.
  ADD CONSTRAINT "Refund_order_fkey"
    FOREIGN KEY ("orderId", "tenantId", "currency")
    REFERENCES "Order"("id", "tenantId", "currency");

COMMIT;
```

## 11. `tests/refund-service.test.ts` — the three that must go red

```ts
// Each has a case that MUST fail and a near-miss that MUST pass. A check that
// has never gone red is a rumour, not a device.
describe("refund devices", () => {
  it("rejects a refund for an order in another tenant", async () => {
    const order = await seedOrder({ tenantId: TENANT_A, totalCents: 5000 });
    const out = await createRefund(deps, cmdFor(order, { tenantId: TENANT_B, amountCents: 100 }));
    expect(out.kind).toBe("order_not_found"); // not 403 — B learns nothing about A
    // near miss: the same call from the owning tenant succeeds
    expect((await createRefund(deps, cmdFor(order, { tenantId: TENANT_A, amountCents: 100 }))).kind)
      .toBe("created");
  });

  it("cannot over-refund under concurrency", async () => {
    const order = await seedOrder({ tenantId: TENANT_A, totalCents: 5000 });
    const results = await Promise.all([
      createRefund(deps, cmdFor(order, { amountCents: 3000, idempotencyKey: "k1" })),
      createRefund(deps, cmdFor(order, { amountCents: 3000, idempotencyKey: "k2" })),
    ]);
    expect(results.filter((r) => r.kind === "created")).toHaveLength(1);
    expect(results.filter((r) => r.kind === "exceeds_refundable")).toHaveLength(1);
    expect(stripe.refunds.create).toHaveBeenCalledTimes(1);
    // near miss: 3000 + 2000 exactly exhausts the order and both succeed
  });

  it("replays instead of re-refunding on a repeated key, and rejects a mutated body", async () => {
    const order = await seedOrder({ tenantId: TENANT_A, totalCents: 5000 });
    const first = await createRefund(deps, cmdFor(order, { amountCents: 1000, idempotencyKey: "k" }));
    const again = await createRefund(deps, cmdFor(order, { amountCents: 1000, idempotencyKey: "k" }));
    expect(again).toMatchObject({ kind: "replayed", refund: { id: first.refund.id } });
    expect(stripe.refunds.create).toHaveBeenCalledTimes(1);
    // near miss: same key, amountCents 2000 => idempotency_key_reused, no Stripe call
    const mutated = await createRefund(deps, cmdFor(order, { amountCents: 2000, idempotencyKey: "k" }));
    expect(mutated.kind).toBe("idempotency_key_reused");
    expect(stripe.refunds.create).toHaveBeenCalledTimes(1);
  });
});
```

## 12. Required config for any of the above to be load-bearing

```jsonc
// tsconfig.json — branded types in a repo that doesn't typecheck in CI are comments
{ "compilerOptions": { "strict": true, "noUncheckedIndexedAccess": true, "exactOptionalPropertyTypes": true } }
```
```jsonc
// .eslintrc — all error, all in the required CI job
{ "rules": {
  "@typescript-eslint/no-floating-promises": "error",   // a lost settle() write
  "@typescript-eslint/switch-exhaustiveness-check": "error",
  "@typescript-eslint/no-explicit-any": "error",
  "require-atomic-updates": "error"
}}
```

---

## What rung each device reached

| Mistake | Device | Rung |
|---|---|---|
| Cross-tenant refund | Compound-unique lookup + `(orderId, tenantId, currency)` FK | **Control** (DB-level) |
| Duplicate refund on retry | Required `IdempotencyKey` + unique index + fingerprint + replay | **Control** |
| Over-refund race | Atomic conditional `UPDATE` + `CHECK` | **Control** |
| Currency mismatch | Currency inside the foreign key | **Control** |
| Refund with no captured payment | `RefundableOrder` as the only accepted argument | **Control** |
| New reason / new outcome unhandled | `assertNever` at both switches | **Control** (build break) |
| Missing Stripe key | Config parsed at boot | **Control** (failed deploy) |
| Nonsense refund state in a row | `CHECK` on SUCCEEDED/FAILED evidence | **Control** |

## What I consciously left possible

1. **A refund can be stranded `PENDING`** if the process dies between the Stripe call and phase 3. The reservation stays held (money isn't over-refunded) but the caller doesn't know the outcome. This needs a **reconciler** — sweep `status='PENDING' AND createdAt < now() - 15 min`, re-drive `stripe.refunds.create` with `idempotencyKey = refund.id` (safe by construction), settle. That's **Detection** rung; the Control-rung alternative is a transactional outbox, which is the right call if you add a second external effect.
2. **Illegal `RefundStatus` transitions are policed in the application**, not the database — a row `CHECK` can see one row's values but not the state it came from. Every transition here is a conditional `updateMany` guarded on `status='PENDING'`, which is a single choke point, but a `psql` session can still write `SUCCEEDED` over `FAILED`. Control needs a trigger or a transition table.
3. **Zero-decimal currencies (JPY, KRW) will be wrong** — `Cents` assumes a 100-minor-unit currency. The `Currency` enum excludes them, so the mistake is currently unrepresentable; adding JPY to that enum without a `minorUnits` type is the trap, and it breaks nothing at compile time.
4. **`amountCents` is `Cents`, not a `Money`**, at the HTTP edge — the currency comes from the order, so a client cannot specify one. That's deliberate (a client-supplied currency is an attack surface), but it means the API can't express a partial refund in a secondary currency.