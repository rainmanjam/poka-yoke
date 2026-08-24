# Grader validation worksheet

60 assertion verdicts, drawn 50/50 on the grader's verdict (which is not shown to you) with seed 20260824. Sample and seed are recorded in sample.jsonl.

For each item: read the response, decide whether the assertion holds, and write `PASS` or `FAIL` on the verdict line. Write `UNCLEAR` if the assertion cannot be decided from the response; those are reported separately and are a finding about the assertion, not about you.

Do not skip items. `--report` refuses to score a partial worksheet, because grading only the easy ones is how a validation comes back clean.

---

## 1. `build-agent-feature|agy-gemini-3.1-pro_with_skill|run-2|5`

**Assertion:** Treats the customer email as untrusted text that could carry instructions

**Verdict:** 

<details><summary>response</summary>

```
Here is the support-email router, built according to the `design` mode Poka-Yoke principles.

### Design Reasoning

**Misuses enumerated:**
1. **Adjacent string parameters (C1):** Passing `body` as `subject` because both are bare strings.
2. **Unvalidated external input (C7):** Webhooks delivering malformed payloads or invalid email addresses.
3. **Stringly-typed LLM outputs (C4):** The LLM hallucinating a team like `"Tech"` or `"Billing"` instead of the exact system strings `"technical"` or `"billing"`.
4. **Non-exhaustive branching (F1):** Adding a new team later and forgetting to update the dispatch logic.
5. **Non-idempotent retryable effects (M2):** The webhook retrying on a timeout and creating two duplicate tickets in the system.

**What the design makes impossible (Control Rung):**
- **Swapping `subject` and `body`** is impossible. `classify_email` uses keyword-only arguments (`*`) and takes a single parsed `IncomingEmail` value object rather than primitive strings.
- **Malformed payloads** are blocked at the boundary by `IncomingEmail.model_validate` using `extra="forbid"` and `EmailStr`.
- **Hallucinated teams** cannot proceed. `Team` is a `Literal[...]`. If the LLM generates a bad team, `RoutingDecision.model_validate()` fails immediately rather than passing corrupted data downstream.
- **Unreachable routing branches** are a compiler error. Using `assert_never()` inside the `match` block ensures `mypy` breaks the build if someone adds `"sales"` to the `Team` literal without handling it here.
- **Duplicate ticket creation** is blocked by making `idempotency_key` a required argument on the external mutation (`submit_to_ticketing`), populated from an assumed `message_id`.

**What is consciously left possible:**
- **LLM validation failures:** If the LLM output violates the schema, the code throws a `ValidationError` (Warning rung: Fail fast and loud). The type system cannot force a non-deterministic LLM to output perfect JSON, so the device moves to runtime. A production system would catch this exception and route the payload to a dead-letter queue (DLQ) for human triage.

### The Code

```python
import json
from typing import Literal, assert_never
from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError
import anthropic

# 1. The Types (Control-rung devices)

# Exhaustive literal. A typo here or an unhandled variant downstream breaks mypy.
Team = Literal["billing", "technical", "account"]

class IncomingEmail(BaseModel):
    """
    Boundary type for incoming emails. 
    frozen=True prevents silent downstream mutation.
    extra='forbid' catches malformed payloads loudly.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    message_id: str = Field(..., min_length=1)  # Assumed necessary for idempotency
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    from_address: EmailStr  # Enforces valid email format at the edge

class RoutingDecision(BaseModel):
    """
    Boundary type for the LLM's output.
    Forces exactly one valid team and a rationale.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    team: Team
    rationale: str = Field(..., description="One-line rationale for the routing decision")


# 2. The Classifier

def classify_email(*, client: anthropic.Anthropic, email: IncomingEmail) -> RoutingDecision:
    """
    Keyword-only arguments prevent parameter swapping.
    Takes a parsed IncomingEmail, returning a parsed RoutingDecision.
    """
    routing_tool = {
        "name": "route_email",
        "description": "Route the customer email to the appropriate team.",
        "input_schema": RoutingDecision.model_json_schema()
    }

    prompt = (
        f"From: {email.from_address}\n"
        f"Subject: {email.subject}\n"
        f"Body:\n{email.body}\n\n"
        "Please route this email to the correct team."
    )

    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
        tools=[routing_tool],
        tool_choice={"type": "tool", "name": "route_email"}
    )

    # Extract the tool use block
    tool_use = next(block for block in response.content if block.type == "tool_use")
    
    # Parse and validate the LLM output. If it hallucinated a wrong team, 
    # Pydantic raises ValidationError (Fail fast and loud).
    return RoutingDecision.model_validate(tool_use.input)


# 3. The Calling Code

def handle_incoming_webhook(*, raw_payload: dict, client: anthropic.Anthropic) -> None:
    """
    Simulates the entry point (e.g., an HTTP request handler).
    """
    try:
        # C7: Parse, don't validate. We only pass the typed object inward.
        email = IncomingEmail.model_validate(raw_payload)
        
        decision = classify_email(client=client, email=email)
        
        # F1: Exhaustive matching. 
        match decision.team:
            case "billing":
                queue = "billing_q"
            case "technical":
                queue = "tech_q"
            case "account":
                queue = "account_q"
            case _:
                # If a developer adds a Team variant but forgets a case here, mypy fails.
                assert_never(decision.team)

        # M2: Required idempotency key for external mutation.
        submit_to_ticketing(
            queue=queue, 
            decision=decision, 
            idempotency_key=email.message_id
        )

    except ValidationError as e:
        # X1: Don't swallow the error. In production, route to a dead-letter queue.
        raise RuntimeError(f"Failed to process email: {e}") from e


def submit_to_ticketing(*, queue: str, decision: RoutingDecision, idempotency_key: str) -> None:
    """
    External write. idempotency_key is required so retries don't double-create tickets.
    """
    pass
```
```

</details>

---

## 2. `build-endpoint|claude-haiku-4-5-20251001_baseline|run-2|7`

**Assertion:** Closes by naming which misuses the design makes impossible

**Verdict:** 

<details><summary>response</summary>

```
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
```

</details>

---

## 3. `retro|opus_baseline|run-1|1`

**Assertion:** Identifies the lookup as a check-then-act race rather than a device

**Verdict:** 

<details><summary>response</summary>

```
Using **poka-yoke:retro**. This repo is the plugin itself, not your payment service — so I can't run the class sweep on your actual code. Answering the judgment question first.

## No. The check cannot fire in the incident it was written for.

**Defect**: 340 customers charged twice.
**Mistake**: retry called `charge()` again with no idempotency key.
**Hazard**: the payment path is not idempotent *as a property* — it depends on a runtime lookup being correct and timely. Nothing structurally prevents two charges.

Walk your fix through the actual timeline:

1. Worker calls Stripe. Stripe **succeeds**. Your client times out waiting on the response.
2. Because it timed out, your code never wrote the charge row.
3. Queue redelivers. Attempt 2 queries "recent charge, same amount" — **and finds nothing**, because attempt 1's row was never written.
4. Charges again.

The check reads a table that is empty by construction in exactly the failing case. It's rung 3 (Detection) wearing a rung 1 costume. Three more holes:

- **TOCTOU.** Redelivery is often concurrent with attempt 1 still in flight. Both read "no charge," both proceed. A check without a unique constraint behind it is a race.
- **Amount is not identity.** A customer legitimately buying twice gets silently *under*-charged. That defect generates no support tickets — you'd never learn it's happening.
- **"Recent" is a magic window.** DLQ replay or a worker restart hours later sails past it.

## What actually closes it

| Device | Rung | Why |
|---|---|---|
| Idempotency key on every Stripe call, derived deterministically from the message/order ID — never random per attempt | **Control** | Stripe dedupes server-side. Attempt 2 gets attempt 1's result back, including when attempt 1 "timed out." |
| Key is a **required** param; `charge()` uncallable without one | **Control** | Removes the affordance, not the instance |
| DB unique constraint on `(order_id, purpose)` | **Control** | Survives key expiry and code paths you didn't think of |
| Write the attempt row **before** calling Stripe | Control | Makes any lookup meaningful; enables recovery-on-timeout |
| Timeout handled as *unknown*, never as *failed* | Control | This is the root belief that produced both incidents |
| Reconciliation job: Stripe charges vs. your ledger, alert on >1/order | Detection | Catches what the above misses |

**The "second time" is the real finding.** The hazard isn't in the worker — it's that your queue is at-least-once and side-effecting consumers aren't idempotent. Every other consumer of that queue has this bug latent: refunds, transfers, provisioning, emails, webhook fanout. That sweep is worth more than the payment fix.

★ Insight ─────────────────────────────────────
A timeout is the one failure that is genuinely *ambiguous* — it tells you nothing about whether the remote side committed. Code that maps timeout→retry is asserting "it didn't happen," which is unprovable. Idempotency keys work precisely because they make that assertion unnecessary.
─────────────────────────────────────────────────

One thing only you can decide: **what the idempotency key is scoped to.** `order_id` blocks a genuine repeat purchase of the same cart; `order_id + attempt_intent` allows it but needs the client to mint the intent. Which is right depends on whether repeat-buy-same-cart is real in your product.

Tell me and I'll write the retro doc plus the regression test that proves the device refuses a redelivery — point me at the service repo and I'll sweep the other consumers too.
```

</details>

---

## 4. `build-form|codex-gpt-5.6-terra_baseline|run-2|0`

**Assertion:** Produces complete, self-contained working code for the described task

**Verdict:** 

<details><summary>response</summary>

```
```tsx
import { useEffect, useMemo, useRef, useState } from "react";

const PAGE_SIZE = 50;

export type Document = {
  id: string;
  title: string;
  updatedAt: string;
  ownerName: string;
};

export type DocumentFilter = {
  search?: string;
  ownerId?: string;
  status?: "active" | "archived";
};

export type DocumentPage = {
  items: Document[];
  page: number; // 1-based
  total: number; // Total documents matching filter
};

type ExplicitSelection = {
  mode: "ids";
  scopeKey: string;
  ids: Set<string>;
};

type AllMatchingSelection = {
  mode: "all-matching";
  scopeKey: string;
  filter: DocumentFilter;
  excludedIds: Set<string>;
};

type Selection = ExplicitSelection | AllMatchingSelection;
type BulkAction = "archive" | "delete";

type DocumentsTableProps = {
  page: DocumentPage;
  filter: DocumentFilter;
  onPageChange: (page: number) => void;
  refresh: () => Promise<void>;
};

function emptySelection(scopeKey: string): ExplicitSelection {
  return { mode: "ids", scopeKey, ids: new Set() };
}

function selectionCount(selection: Selection, total: number) {
  return selection.mode === "ids"
    ? selection.ids.size
    : Math.max(0, total - selection.excludedIds.size);
}

function isSelected(selection: Selection, id: string) {
  return selection.mode === "ids"
    ? selection.ids.has(id)
    : !selection.excludedIds.has(id);
}

function selectionPayload(selection: Selection) {
  if (selection.mode === "ids") {
    return {
      kind: "ids" as const,
      ids: [...selection.ids],
    };
  }

  return {
    kind: "matching-filter" as const,
    filter: selection.filter,
    excludedIds: [...selection.excludedIds],
  };
}

/*
  Expected server contract:

  POST /api/documents/bulk/archive
  POST /api/documents/bulk/delete

  {
    selection:
      | { kind: "ids", ids: string[] }
      | {
          kind: "matching-filter",
          filter: DocumentFilter,
          excludedIds: string[]
        }
  }

  The server must evaluate matching-filter selections server-side. This avoids
  sending thousands of document IDs when the user selects every matching result.
*/
async function mutateDocuments(
  action: BulkAction,
  selection: Selection,
): Promise<{ affected: number }> {
  const response = await fetch(`/api/documents/bulk/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selection: selectionPayload(selection) }),
  });

  const body = (await response.json().catch(() => null)) as
    | { affected?: number; error?: string }
    | null;

  if (!response.ok) {
    throw new Error(body?.error ?? `Could not ${action} documents.`);
  }

  return { affected: body?.affected ?? 0 };
}

function TableCheckbox({
  checked,
  indeterminate = false,
  disabled = false,
  label,
  onChange,
}: {
  checked: boolean;
  indeterminate?: boolean;
  disabled?: boolean;
  label: string;
  onChange: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (inputRef.current) inputRef.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <input
      ref={inputRef}
      type="checkbox"
      checked={checked}
      disabled={disabled}
      aria-label={label}
      onChange={onChange}
      className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
    />
  );
}

export function DocumentsTable({
  page,
  filter,
  onPageChange,
  refresh,
}: DocumentsTableProps) {
  // This intentionally excludes page number, so selections persist across pages.
  const scopeKey = useMemo(() => JSON.stringify(filter), [filter]);
  const [selection, setSelection] = useState<Selection>(() =>
    emptySelection(scopeKey),
  );
  const [pendingAction, setPendingAction] = useState<BulkAction | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  // A changed search/filter represents a different result set, so clear selection.
  useEffect(() => {
    setSelection(emptySelection(scopeKey));
    setNotice("");
    setError("");
  }, [scopeKey]);

  const selectedCount = selectionCount(selection, page.total);
  const pageRowsSelected =
    page.items.length > 0 &&
    page.items.every((document) => isSelected(selection, document.id));
  const somePageRowsSelected =
    !pageRowsSelected &&
    page.items.some((document) => isSelected(selection, document.id));
  const pending = pendingAction !== null;
  const totalPages = Math.max(1, Math.ceil(page.total / PAGE_SIZE));

  function toggleDocument(id: string) {
    setSelection((current) => {
      if (current.scopeKey !== scopeKey) return emptySelection(scopeKey);

      if (current.mode === "ids") {
        const ids = new Set(current.ids);
        ids.has(id) ? ids.delete(id) : ids.add(id);
        return { ...current, ids };
      }

      const excludedIds = new Set(current.excludedIds);
      excludedIds.has(id) ? excludedIds.delete(id) : excludedIds.add(id);
      return { ...current, excludedIds };
    });
  }

  function toggleCurrentPage() {
    setSelection((current) => {
      if (current.scopeKey !== scopeKey) return emptySelection(scopeKey);

      if (current.mode === "ids") {
        const ids = new Set(current.ids);

        for (const document of page.items) {
          pageRowsSelected ? ids.delete(document.id) : ids.add(document.id);
        }

        return { ...current, ids };
      }

      const excludedIds = new Set(current.excludedIds);

      for (const document of page.items) {
        pageRowsSelected
          ? excludedIds.add(document.id)
          : excludedIds.delete(document.id);
      }

      return { ...current, excludedIds };
    });
  }

  function selectAllMatching() {
    setSelection({
      mode: "all-matching",
      scopeKey,
      filter: { ...filter },
      excludedIds: new Set(),
    });
  }

  async function runBulkAction(action: BulkAction) {
    if (selectedCount === 0 || pending) return;

    if (
      action === "delete" &&
      !window.confirm(
        `Permanently delete ${selectedCount.toLocaleString()} document${
          selectedCount === 1 ? "" : "s"
        }?`,
      )
    ) {
      return;
    }

    setPendingAction(action);
    setError("");
    setNotice("");

    try {
      const result = await mutateDocuments(action, selection);
      const affected = result.affected || selectedCount;

      setSelection(emptySelection(scopeKey));
      setNotice(
        `${action === "archive" ? "Archived" : "Deleted"} ${affected.toLocaleString()} document${
          affected === 1 ? "" : "s"
        }.`,
      );
      await refresh();
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Something went wrong. Please try again.",
      );
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <section className="space-y-4">
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th className="w-12 px-4 py-3 text-left">
                  <TableCheckbox
                    checked={pageRowsSelected}
                    indeterminate={somePageRowsSelected}
                    disabled={pending || page.items.length === 0}
                    label="Select all documents on this page"
                    onChange={toggleCurrentPage}
                  />
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Document
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Owner
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Updated
                </th>
              </tr>
            </thead>

            <tbody className="divide-y divide-slate-100">
              {page.items.map((document) => (
                <tr
                  key={document.id}
                  className={
                    isSelected(selection, document.id)
                      ? "bg-indigo-50/60"
                      : "hover:bg-slate-50"
                  }
                >
                  <td className="px-4 py-4">
                    <TableCheckbox
                      checked={isSelected(selection, document.id)}
                      disabled={pending}
                      label={`Select ${document.title}`}
                      onChange={() => toggleDocument(document.id)}
                    />
                  </td>
                  <td className="px-4 py-4 font-medium text-slate-900">
                    {document.title}
                  </td>
                  <td className="px-4 py-4 text-sm text-slate-600">
                    {document.ownerName}
                  </td>
                  <td className="px-4 py-4 text-sm text-slate-600">
                    {new Intl.DateTimeFormat(undefined, {
                      dateStyle: "medium",
                    }).format(new Date(document.updatedAt))}
                  </td>
                </tr>
              ))}

              {page.items.length === 0 && (
                <tr>
                  <td
                    colSpan={4}
                    className="px-4 py-12 text-center text-sm text-slate-500"
                  >
                    No documents match this filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3">
          <p className="text-sm text-slate-600">
            {page.total.toLocaleString()} matching document
            {page.total === 1 ? "" : "s"}
          </p>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={pending || page.page <= 1}
              onClick={() => onPageChange(page.page - 1)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-sm text-slate-600">
              Page {page.page} of {totalPages}
            </span>
            <button
              type="button"
              disabled={pending || page.page >= totalPages}
              onClick={() => onPageChange(page.page + 1)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {selectedCount > 0 && (
        <div
          aria-live="polite"
          className="sticky bottom-4 flex flex-col gap-3 rounded-xl border border-indigo-200 bg-white p-4 shadow-lg sm:flex-row sm:items-center sm:justify-between"
        >
          <div>
            <p className="font-semibold text-slate-900">
              {selectedCount.toLocaleString()} document
              {selectedCount === 1 ? "" : "s"} selected
            </p>

            {selection.mode === "ids" &&
              pageRowsSelected &&
              page.total > page.items.length && (
                <button
                  type="button"
                  disabled={pending}
                  onClick={selectAllMatching}
                  className="mt-1 text-sm font-medium text-indigo-700 hover:text-indigo-800 hover:underline disabled:opacity-50"
                >
                  Select all {page.total.toLocaleString()} matching documents
                </button>
              )}

            {selection.mode === "all-matching" && (
              <p className="mt-1 text-sm text-slate-600">
                All matching documents are selected. Unchecking a row excludes
                it.
              </p>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={pending}
              onClick={() => setSelection(emptySelection(scopeKey))}
              className="rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
            >
              Clear
            </button>
            <button
              type="button"
              disabled={pending}
              onClick={() => runBulkAction("archive")}
              className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {pendingAction === "archive" ? "Archiving…" : "Archive"}
            </button>
            <button
              type="button"
              disabled={pending}
              onClick={() => runBulkAction("delete")}
              className="rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {pendingAction === "delete" ? "Deleting…" : "Delete"}
            </button>
          </div>
        </div>
      )}

      {(notice || error) && (
        <p
          role={error ? "alert" : "status"}
          className={error ? "text-sm text-red-700" : "text-sm text-emerald-700"}
        >
          {error || notice}
        </p>
      )}
    </section>
  );
}
```
```

</details>

---

## 5. `llm|claude-sonnet-5_with_skill|run-7|6`

**Assertion:** Identifies prompt injection risk from the customer-supplied message reaching a privileged action

**Verdict:** 

<details><summary>response</summary>

```
Using the poka-yoke `llm` skill for this — it's an AI feature already in production causing real incidents, so this is audit voice, not build voice.

**The core problem: both of your fixes are rung zero.** "Be careful to extract the exact amount" and "never refund the same order twice" are instructions to a component that has a non-zero error rate on every single call. No prompt wording drives that to zero — it's not a bug in your prompt, it's the nature of the material. You need devices *outside* the model, not better wording inside it.

### 1. Wrong refund amount
**Mistake**: model mis-extracts an amount from ambiguous chat text (e wrong currency, misread digit, hallucinated number).
**Consequence**: refund API gets called with a plausible-looking but wrong number — silent, no error, money moves.
**Today**: None (prompt wording only).
**Device**:
- Use structured/constrained output (schema: `amount: float`, `reason: enum[...]`) instead of parsing prose — this closes the "malformed output" half.
- The half the schema *can't* catch: is the number *correct*. For that, don't trust the model's number as authorization — validate server-side against the actual order: `amount <= order.refundable_balance`, and ideally `amount == order.total` unless the model also returns a specific line-item reason that justifies a partial. The model proposes; your system disposes. → **Control** on "an invented amount reaches Stripe," **Warning at best** on "is this the *right* amount for a legitimate partial refund," which may need a human confirmation step for anything above a threshold or below full amount.

### 2. Double refund on the same order
**Mistake**: the bot (or a retry, or a queue redelivery, or the user re-describing the same complaint two messages later) issues a second refund call for an order that already got one.
**Consequence**: double payout, silent until finance notices.
**Today**: None — "never refund twice" is a sentence in a system prompt, not a check.
**Device**: idempotency key on every refund call, keyed on order ID (or order ID + reason), backed by a unique constraint at the API/DB layer — the same pattern as payment retries. This makes the second call fail loudly or no-op instead of succeeding twice, regardless of whether the model "remembers" it already did this earlier in the conversation. → **Control**.

### Also worth closing while you're in there
- **Tight tool schema**: `refund(order_id: str, amount: float, reason: enum[...])` — no free-text field the model can use to smuggle extra intent, `amount` bounded to the order's refundable range if your framework supports range constraints.
- **Confirmation gate for irreversible action**: since a refund is money leaving and hard to reverse, consider requiring either a second deterministic check (amount matches order records exactly) or human approval above some dollar threshold, rather than trusting the model's decision to fire the tool at all.
- **Turn both production incidents into eval cases**: the specific chat messages that caused the wrong amount and the double refund become permanent regression tests in your eval suite, run in CI on every prompt/model change. That's the only way you'll know a future prompt tweak didn't reopen the same hole.

The prompt edits aren't wasted — keep them, they reduce frequency — but the amount validation and the idempotency key are what actually make the two incidents you already had impossible to repeat, not just less likely.
```

</details>

---

## 6. `ux|opus_baseline|run-5|3`

**Assertion:** Recommends grace-period undo as a strong low-friction option

**Verdict:** 

<details><summary>response</summary>

```
Honest answer: no, not on its own. And we actually landed on this earlier today (05:18–06:00) — worth not re-deciding it from scratch.

## Why the modal is the weakest option

A confirmation dialog is rung 0 on the poka-yoke ladder — it relies on the user *reading*. The specific failure mode is click-through blindness: anyone who sees "Are you sure?" more than a few times develops a reflex, and the reflex fires exactly when they're moving fast, which is exactly when the accidental deletes happen. You'd add friction to every legitimate delete and still get the panic emails.

There's also a tell in your own description: users email support **in a panic**. That's not a signal they needed a better warning — it's a signal the action is *unrecoverable*. The modal addresses the wrong half.

`★ Insight ─────────────────────────────────────`
- "Are you sure?" asks about the user's **resolve**. Their resolve was never in question — they meant to click something, just not *that*. A device that names facts ("Delete 3 projects and 1,204 files?") does fixed-value inspection; one that asks about intent does nothing.
- Reversibility is a backend change, which is why teams reach for the modal instead. The modal is cheap and visible; soft-delete is the actual fix.
`─────────────────────────────────────────────────`

## What I'd build instead

1. **Soft-delete + 30-day trash.** Workspace flips to `deleted_at`, disappears from the UI, purges on a timer. The mistake now has no permanent consequence.
2. **Undo toast.** "Workspace deleted. Undo" for ~10s. Zero friction on the happy path, full recovery on the mistaken one. This is what kills the support emails.
3. **Type-to-confirm on the *purge*** — the one genuinely irreversible step. GitHub-style, type the workspace name. Rare enough that it can't become reflex.

Net effect: the common path gets *faster* than your modal, and the panic email stops existing.

## Three decisions I need from you

These are genuinely yours — they're product/billing calls, not engineering ones, and they were the blockers last time:

**1. Billing and seats during the grace period.** Does a trashed workspace keep consuming seats and billing? Charging for a deleted thing generates a different support email; not charging means restore might fail if they've since downgraded.

**2. Slug reuse.** Is the workspace slug freed immediately on delete, or held for the 30 days? Freeing it is friendlier for someone recreating; holding it is what makes restore actually work.

**3. Who can restore.** Only the deleter? Any workspace admin? Org owners? This matters most when the person who fat-fingered it has already left.

Tell me where the delete handler lives and how you want those three to land, and I'll write it. If you'd rather ship the modal today as a stopgap while the soft-delete lands, say so — I'll build it with the specific-consequence copy ("Delete *Acme Prod* — 12 projects, 340 files?") rather than "Are you sure?", so it's at least doing real work.
```

</details>

---

## 7. `data|agy-gemini-3.1-pro_with_skill|run-1|3`

**Assertion:** Recommends that assertions run before publication rather than after, so bad data cannot reach the dashboard

**Verdict:** 

<details><summary>response</summary>

```
## Goal Description
Conduct a Poka-Yoke retro and implement preventative devices for the recent revenue dashboard incident. The incident occurred because an upstream team renamed a column, causing a join to return nulls, which were silently coalesced to 0 for three weeks. The proposed plan moves beyond the currently implemented "not empty" test to address the systemic hazard.

## User Review Required
> [!WARNING]
> The current "not empty" test you added **would have passed** during this incident. Because the pipeline coalesced nulls to 0, the table was populated with rows, just with $0 revenue. A "not empty" check does not catch zeroed-out data.

> [!IMPORTANT]
> The fixes proposed here will require changing how the pipeline runs (e.g., building to staging first, or failing the pipeline on schema drift). Please review these architectural changes.

## Open Questions
- What data warehouse and pipeline tool (e.g., dbt, Airflow, Snowflake) are you using? This will determine the exact syntax for the constraints.
- Do we have access to the source system's total revenue to set up a reconciliation check?

## Proposed Changes

Following the `retro` and `data` Poka-Yoke skills, we separate the incident into three parts:
- **The defect:** Revenue was reported incorrectly (low) for three weeks.
- **The mistake:** Upstream renamed a column, breaking our join.
- **The hazard:** The pipeline silently accepted a missing upstream column, and `COALESCE` acted as a silent `except: pass`, masking the missing data.

Here is the implementation plan to install devices from strongest (Control) to weakest (Detection).

### 1. Ingest Data Contracts (Control)
We must catch the missing/renamed column at the boundary, before it reaches the join.
- **Action:** Implement a schema validation check on the raw source table.
- **Device:** If the expected revenue column is missing or changes type, the pipeline must **fail and quarantine** the run immediately. A rename must be treated as a breaking change, not a silent null.

### 2. Pipeline Assertions (Warning / Control)
The pipeline must stop if the data is malformed, rather than pushing bad data to the dashboard.
- **Action:** Assert the null-rate of the raw joined column *before* the `COALESCE` is applied. 
- **Device:** Build the data to a staging table. Run a test that asserts `COUNT(revenue_col) / COUNT(*) > 0.99` (or whatever threshold is appropriate). Only promote the staging table to production if this test passes. 

### 3. Reconciliation Check (Detection)
A check for "not empty" only verifies volume, not correctness.
- **Action:** Implement a reconciliation query.
- **Device:** "Does it agree?" Compare the total revenue sum in the warehouse against the source billing system. This is the only check that catches logic errors (like a bad join) even when the schema is perfectly valid.

### 4. Class Sweep
A poka-yoke that fixes one call site is not a poka-yoke. We need to find everywhere else this hazard exists.
- **Action:** Audit the codebase for other instances of `COALESCE(col, 0)` on upstream joins that feed critical or financial metrics, where a missing column would be silently masked.

## Verification Plan

### Automated Tests
- Run the pipeline against a mock upstream table where the column has been renamed. Verify that the pipeline **fails** at the ingest contract stage, rather than succeeding with 0s.
- Verify the null-rate assertion fails the staging build if we manually inject nulls.

### Manual Verification
- Review the class sweep results to ensure all similar `COALESCE` hazards are identified and ticketed.
- Verify the reconciliation check accurately flags a deliberate 1% discrepancy.
```

</details>

---

## 8. `data|codex-gpt-5.6-terra_with_skill|run-1|2`

**Assertion:** Recommends reconciliation against a source of truth, not only shape checks

**Verdict:** 

<details><summary>response</summary>

```
No. A non-empty-table test would likely have passed during this incident: rows still existed, and `COALESCE(..., 0)` turned missing join results into plausible revenue values.

The hazard is: the pipeline can treat “unknown because the join broke” as “real zero revenue,” then publish it.

Keep the non-empty check, but add these as blocking checks on the staging model before dashboard publication:

- A source data contract: required upstream column, type, and version must be present. A rename fails ingestion instead of becoming nulls. This is a **Warning** device; a producer-side versioned contract/gate is closer to **Control**.
- A join-integrity assertion before any `COALESCE`: `unmatched_join_count = 0` (or an explicitly agreed, tightly bounded exception rate). Never turn join-generated nulls into zero without recording and checking the reason.
- A reconciliation: compare dashboard revenue to an independent source-of-truth aggregate for the same period, with a small defined tolerance. This is the check most likely to catch a well-shaped but logically wrong join.
- Volume/cardinality guards: historical weekday-aware row and revenue floors/ceilings, plus uniqueness checks on the revenue grain. These catch partial or fan-out joins.

Build → validate staging → promote only on pass. If validation fails, retain the last known-good published table and visibly mark it stale rather than publishing zeros.

Prove each device can fail: rename the source column, create an unmatched key, and alter the source total; each should block promotion. Also verify that a legitimate zero-revenue row still passes.
```

</details>

---

## 9. `data|claude-sonnet-5_baseline|run-1|3`

**Assertion:** Recommends that assertions run before publication rather than after, so bad data cannot reach the dashboard

**Verdict:** 

<details><summary>response</summary>

```
No — that test would have stayed green through the entire three-week incident.

**Why it doesn't catch this:** the join returning nulls didn't shrink the table, it just filled a column with wrong values. Row count was probably identical to a healthy day. "Not empty" only answers the first, weakest form of *is it there* — it can't answer the question that actually mattered here: **does it agree** with the source system.

Walking your incident through the four checks:
- **Is it there?** Table populated, on time. Passes.
- **Right amount?** Same row count as always (it's a null-filling bug, not a row-dropping one). Passes.
- **Shaped right?** `revenue` is a valid number — 0 is a legal value. Passes.
- **Does it agree?** This is the one that would have failed, and it's the one you don't have.

Two devices, in priority order:

1. **Reconciliation on the revenue table**: sum(revenue) in the warehouse vs. the equivalent total pulled from the source system (or upstream table pre-join), daily, with a tolerance band. This is the only check that catches a wrong `JOIN` — everything else validates shape, not correctness. This directly targets what broke: the column rename nobody announced.
2. **Kill the silent COALESCE**: `COALESCE(revenue, 0)` is doing the same thing as `except: pass` — it took a loud failure (null propagating, dashboard breaking visibly) and converted it into a quiet, plausible-looking wrong number. Replace it with an assertion on null rate for the join key *before* the coalesce (e.g., `null_rate(revenue) < 1%`, alert/fail above that), or route unmatched rows to a quarantine table instead of defaulting them to zero.

If you want the durable fix instead of a patch: this is a missing data contract on the upstream column. A rename should have broken the pipeline loudly at ingest, not degraded it silently three joins downstream — that's the difference between Warning-rung and nothing at all.
```

</details>

---

## 10. `retro|codex-gpt-5.6-terra_baseline|run-1|4`

**Assertion:** Separates the defect from the mistake from the underlying system hazard

**Verdict:** 

<details><summary>response</summary>

```
No. The “same recent amount” lookup is a temporary tripwire, not a payment-safety guarantee:

- It races: two workers can both look, see nothing, then both charge.
- It blocks legitimate equal-amount purchases by the same customer.
- It cannot distinguish retries from separate business transactions.
- It will fail again under delayed Stripe visibility, concurrent delivery, or a retry outside its lookback window.

The durable fix is idempotency tied to the business operation—not to a queue delivery or worker attempt.

1. Create one permanent `payment_operation` per order/invoice, with a unique database constraint on its business ID.
2. Persist a stable Stripe idempotency key and, preferably, the Stripe PaymentIntent ID on that operation *before* allowing retries.
3. Every redelivery retries the same PaymentIntent/request using the same idempotency key—never creates a new charge/payment intent.
4. On a timeout, treat the outcome as **unknown**, not failed: retrieve/reconcile the existing Stripe object, then retry the exact same request/key if appropriate.
5. Use Stripe webhooks plus periodic reconciliation to settle the local operation state; attach your operation ID in Stripe metadata for recovery/audit.

Stripe explicitly recommends idempotency keys for retry-safe POSTs and says a network timeout should be retried with the *same* key. Its PaymentIntents guidance also says to reuse the same PaymentIntent for an interrupted payment. [Stripe idempotent requests](https://docs.stripe.com/api/idempotent_requests?lang=curl), [Stripe advanced error handling](https://docs.stripe.com/error-low-level), [Stripe PaymentIntents](https://docs.stripe.com/payments/payment-intents)

For today: disable automatic queue retries for ambiguous payment outcomes and route those jobs to reconciliation/manual review until the above invariant is live. Keep the “same amount” check only as an alerting guardrail, never the authorization to charge or suppress a charge.

Because this is recurrence #2, prove the fix with fault-injection tests: force a timeout after Stripe accepts the request, simultaneous duplicate deliveries, worker crash before/after persisting state, and delayed webhooks. Each must show exactly one successful charge for one payment operation.
```

</details>

---

## 11. `build-endpoint|codex-gpt-5.6-terra_with_skill|run-3|2`

**Assertion:** Backs idempotency with a database unique constraint, not application logic alone

**Verdict:** 

<details><summary>response</summary>

```
Assumptions: Express, `zod`, UUID primary keys, and a required `Idempotency-Key` header. `Order` stores the Stripe PaymentIntent ID used for refunds.

```ts
// src/refunds.ts
import type { Request, Response, Router } from "express";
import { Prisma, PrismaClient, RefundReason, RefundStatus } from "@prisma/client";
import Stripe from "stripe";
import { z } from "zod";

type Session = {
  userId: string;
  tenantId: string;
};

type AuthenticatedRequest = Request & {
  session?: Session;
};

export class HttpError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

const refundBodySchema = z
  .object({
    orderId: z.string().uuid(),
    amountCents: z.number().int().positive().max(100_000_000),
    reason: z.enum([
      RefundReason.duplicate,
      RefundReason.fraudulent,
      RefundReason.requested_by_customer,
    ]),
  })
  .strict();

const sessionSchema = z.object({
  userId: z.string().min(1).max(255),
  tenantId: z.string().uuid(),
});

const idempotencyKeySchema = z.string().trim().min(1).max(255);

function isSerializationFailure(error: unknown): boolean {
  return (
    error instanceof Prisma.PrismaClientKnownRequestError &&
    error.code === "P2034"
  );
}

async function serializableRetry<T>(
  prisma: PrismaClient,
  action: (tx: Prisma.TransactionClient) => Promise<T>,
): Promise<T> {
  let lastError: unknown;

  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return await prisma.$transaction(action, {
        isolationLevel: Prisma.TransactionIsolationLevel.Serializable,
        maxWait: 5_000,
        timeout: 30_000,
      });
    } catch (error) {
      lastError = error;
      if (!isSerializationFailure(error) || attempt === 2) throw error;
    }
  }

  throw lastError;
}

function reservationStatus(stripeStatus: Stripe.Refund.Status): RefundStatus {
  switch (stripeStatus) {
    case "succeeded":
      return RefundStatus.succeeded;
    case "failed":
      return RefundStatus.failed;
    case "canceled":
      return RefundStatus.canceled;
    case "requires_action":
      return RefundStatus.requires_action;
    case "pending":
    default:
      // An unknown future Stripe state remains reserved until reconciliation.
      return RefundStatus.pending;
  }
}

export function registerRefundRoutes(
  router: Router,
  dependencies: {
    prisma: PrismaClient;
    stripe: Stripe;
  },
): void {
  const { prisma, stripe } = dependencies;

  router.post(
    "/refunds",
    async (req: AuthenticatedRequest, res: Response): Promise<void> => {
      const session = sessionSchema.safeParse(req.session);
      if (!session.success) {
        throw new HttpError(401, "Authentication is required.");
      }

      const body = refundBodySchema.safeParse(req.body);
      if (!body.success) {
        throw new HttpError(400, "Invalid refund request.");
      }

      const idempotencyKey = idempotencyKeySchema.safeParse(
        req.get("Idempotency-Key"),
      );
      if (!idempotencyKey.success) {
        throw new HttpError(
          400,
          "A non-empty Idempotency-Key header of at most 255 characters is required.",
        );
      }

      const { userId, tenantId } = session.data;
      const { orderId, amountCents, reason } = body.data;

      const result = await serializableRetry(prisma, async (tx) => {
        // RLS is transaction-local, so a pooled connection cannot inherit another tenant.
        await tx.$executeRaw`
          SELECT set_config('app.tenant_id', ${tenantId}, true)
        `;

        // The row lock serializes all refund calculations for this order.
        // RLS makes another tenant's order invisible, producing the same 404.
        const orders = await tx.$queryRaw<
          Array<{
            id: string;
            totalCents: number;
            currency: string;
            stripePaymentIntentId: string | null;
          }>
        >`
          SELECT
            "id",
            "totalCents",
            "currency",
            "stripePaymentIntentId"
          FROM "Order"
          WHERE "id" = ${orderId}
          FOR UPDATE
        `;

        const order = orders[0];
        if (!order) {
          throw new HttpError(404, "Order not found.");
        }

        if (!order.stripePaymentIntentId) {
          throw new HttpError(
            409,
            "This order has no refundable Stripe payment.",
          );
        }

        const existing = await tx.refund.findUnique({
          where: {
            orderId_idempotencyKey: {
              orderId,
              idempotencyKey: idempotencyKey.data,
            },
          },
        });

        if (existing) {
          if (
            existing.amountCents !== amountCents ||
            existing.reason !== reason
          ) {
            throw new HttpError(
              409,
              "This Idempotency-Key was already used with different refund details.",
            );
          }

          return { refund: existing, replayed: true };
        }

        const reserved = await tx.refund.aggregate({
          where: {
            orderId,
            status: {
              in: [
                RefundStatus.pending,
                RefundStatus.requires_action,
                RefundStatus.succeeded,
              ],
            },
          },
          _sum: { amountCents: true },
        });

        const remainingCents =
          order.totalCents - (reserved._sum.amountCents ?? 0);

        if (amountCents > remainingCents) {
          throw new HttpError(422, "Refund amount exceeds the remaining balance.");
        }

        let stripeRefund: Stripe.Refund;
        try {
          stripeRefund = await stripe.refunds.create(
            {
              payment_intent: order.stripePaymentIntentId,
              amount: amountCents,
              reason,
              metadata: {
                orderId,
                tenantId,
                requestedByUserId: userId,
              },
            },
            { idempotencyKey: idempotencyKey.data },
          );
        } catch (error) {
          if (error instanceof Stripe.errors.StripeError) {
            throw new HttpError(422, "Stripe rejected the refund request.");
          }
          throw error;
        }

        const refund = await tx.refund.create({
          data: {
            orderId,
            amountCents,
            reason,
            idempotencyKey: idempotencyKey.data,
            stripeRefundId: stripeRefund.id,
            stripeStatus: stripeRefund.status,
            status: reservationStatus(stripeRefund.status),
          },
        });

        return { refund, replayed: false };
      });

      res.status(result.replayed ? 200 : 201).json(result.refund);
    },
  );
}
```

```prisma
// prisma/schema.prisma — relevant models/additions

enum RefundReason {
  duplicate
  fraudulent
  requested_by_customer
}

enum RefundStatus {
  pending
  requires_action
  succeeded
  failed
  canceled
}

model Order {
  id                    String   @id @default(uuid()) @db.Uuid
  tenantId              String   @db.Uuid
  totalCents            Int
  currency              String   @db.Char(3)
  stripePaymentIntentId String?  @unique
  refunds               Refund[]

  @@index([tenantId])
}

model Refund {
  id             String       @id @default(uuid()) @db.Uuid
  orderId        String       @db.Uuid
  amountCents    Int
  reason         RefundReason
  status         RefundStatus @default(pending)
  stripeStatus   String
  stripeRefundId String       @unique
  idempotencyKey String
  createdAt      DateTime     @default(now())

  order Order @relation(fields: [orderId], references: [id], onDelete: Restrict)

  @@unique([orderId, idempotencyKey])
  @@index([orderId, status])
}
```

```sql
-- prisma/migrations/20260822000000_add_refund_safety/migration.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TYPE "RefundReason" AS ENUM (
  'duplicate',
  'fraudulent',
  'requested_by_customer'
);

CREATE TYPE "RefundStatus" AS ENUM (
  'pending',
  'requires_action',
  'succeeded',
  'failed',
  'canceled'
);

ALTER TABLE "Order"
  ADD COLUMN "stripePaymentIntentId" TEXT;

CREATE UNIQUE INDEX "Order_stripePaymentIntentId_key"
  ON "Order"("stripePaymentIntentId");

ALTER TABLE "Refund"
  ALTER COLUMN "reason" TYPE "RefundReason"
  USING "reason"::"RefundReason",
  ADD COLUMN "status" "RefundStatus" NOT NULL DEFAULT 'pending',
  ADD COLUMN "stripeStatus" TEXT NOT NULL DEFAULT 'pending',
  ADD COLUMN "stripeRefundId" TEXT,
  ADD COLUMN "idempotencyKey" TEXT;

ALTER TABLE "Refund"
  ALTER COLUMN "stripeRefundId" SET NOT NULL,
  ALTER COLUMN "idempotencyKey" SET NOT NULL;

ALTER TABLE "Refund"
  ADD CONSTRAINT "Refund_orderId_fkey"
    FOREIGN KEY ("orderId") REFERENCES "Order"("id")
    ON DELETE RESTRICT ON UPDATE CASCADE;

CREATE UNIQUE INDEX "Refund_stripeRefundId_key"
  ON "Refund"("stripeRefundId");

CREATE UNIQUE INDEX "Refund_orderId_idempotencyKey_key"
  ON "Refund"("orderId", "idempotencyKey");

CREATE INDEX "Refund_orderId_status_idx"
  ON "Refund"("orderId", "status");

-- The application database role must be non-superuser, NOBYPASSRLS, and not
-- own these tables. set_config(..., true) in the handler scopes this to one tx.
ALTER TABLE "Order" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "Order" FORCE ROW LEVEL SECURITY;

CREATE POLICY "order_tenant_isolation" ON "Order"
  USING ("tenantId" = current_setting('app.tenant_id', true)::uuid)
  WITH CHECK ("tenantId" = current_setting('app.tenant_id', true)::uuid);

ALTER TABLE "Refund" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "Refund" FORCE ROW LEVEL SECURITY;

CREATE POLICY "refund_tenant_isolation" ON "Refund"
  USING (
    EXISTS (
      SELECT 1
      FROM "Order"
      WHERE "Order"."id" = "Refund"."orderId"
        AND "Order"."tenantId" = current_setting('app.tenant_id', true)::uuid
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1
      FROM "Order"
      WHERE "Order"."id" = "Refund"."orderId"
        AND "Order"."tenantId" = current_setting('app.tenant_id', true)::uuid
    )
  );
```

The control devices are: tenant RLS plus session-derived scoping prevents cross-tenant refunds; the locked order row and reserved-refund aggregate prevent concurrent over-refunds; and the required, payload-bound idempotency key prevents duplicate refunds on retries. Stripe supports idempotent POSTs and the listed refund reasons. [Stripe refund API](https://docs.stripe.com/api/refunds/create?lang=curl) [Stripe idempotency](https://docs.stripe.com/api/idempotent_requests?lang=curl)

A Stripe webhook should subsequently update `Refund.status`/`stripeStatus` for asynchronous failures or cancellations; keeping `pending` refunds reserved is the safe default until that reconciliation occurs.
```

</details>

---

## 12. `audit|claude-sonnet-5_with_skill|run-5|0`

**Assertion:** Flags that transfer()'s fromAccount and toAccount are both plain strings and can be swapped silently

**Verdict:** 

<details><summary>response</summary>

```
One heads-up before the findings: this file's header comment says it's a **deliberately hazard-rich eval fixture** used to benchmark this very skill (`benchmarks/fixtures/`), not the actual billing module. If there's a real billing module elsewhere that this stands in for, point me at it — everything below is real and worth fixing regardless, but "before we ship it" doesn't quite apply to a benchmark fixture.

Scope: `benchmarks/fixtures/payments.ts` in full (105 lines, read directly — the hazard detector script needed interactive approval I didn't get, so this is manual application of the three lenses). Ranked by blast radius × ease of mistake.

## 1. `handleWebhook` charges money with no signature verification — Money/Security · Trivial
**Where**: `benchmarks/fixtures/payments.ts:93-100`
**Mistake**: `JSON.parse(body)` is trusted directly — `event.data.customer` and `event.data.amount` flow straight into a real Stripe charge with no HMAC/signature check against Stripe's webhook secret, and no schema validation.
**Consequence**: anyone who can reach this endpoint can POST a fake `invoice.paid` event and charge an arbitrary Stripe customer an arbitrary amount. Silent — it looks like a normal successful charge.
**Today**: None.
**Device**: verify `stripe-signature` via `stripe.webhooks.constructEvent(body, sig, secret)` before touching the payload, and parse the result through a schema (zod) instead of trusting `any`. → **Control** on both the auth bypass and the unvalidated-input hazard (C7).

## 2. `chargeCustomer` has no idempotency key — Money · Automatic (no misuse needed)
**Where**: `benchmarks/fixtures/payments.ts:37-61`
**Mistake**: `stripe.charges.create` is called with no idempotency key, and it's reachable both from `handleWebhook` (Stripe webhooks are at-least-once by design — redelivery is normal, not edge-case) and from the function's own internal retry (`retry: true` calls itself again with a fresh network round-trip, no key tying the two attempts together).
**Consequence**: ordinary webhook redelivery or a transient network blip on the retry path double-charges the customer. Worse, on failure the catch block returns `null` with no logging and no rethrow — `handleWebhook` never checks the return, so a *failed* charge for an invoice Stripe considers paid vanishes silently too.
**Today**: None (retry flag is the opposite of a device — it's rung 0 wearing a costume, per M2 in the hazard catalog).
**Device**: require an `idempotencyKey` parameter, pass it as `stripe.charges.create(..., { idempotencyKey })`, derive it from the Stripe event ID in `handleWebhook`. → **Control**. Also stop swallowing the error — log and rethrow, don't return `null`.

## 3. `transfer` — swappable accounts, no transaction, check-then-act race — Money/Data corruption · Silent
**Where**: `benchmarks/fixtures/payments.ts:17-35`
**Mistake**: `fromAccount`/`toAccount` are adjacent same-type strings (swap compiles and passes review). Separately: balance is read, then two `update` calls happen outside a transaction — a crash or two concurrent transfers between the read and the writes can leave money created or destroyed, and nothing stops a second concurrent call from reading the same stale balance and also passing the funds check.
**Consequence**: ledger goes out of balance, silently, only found on reconciliation.
**Today**: None.
**Device**: wrap both updates in a single DB transaction with a `WHERE balance >= amount` conditional update (turns the race into an atomic compare-and-swap) → **Control** for the transaction/race. For the swap: branded `AccountId` type distinguishing nothing structurally (both are accounts) — realistically here named/keyword args are the practical fix → **Warning**.

## 4. `purgeCanceledAccounts()` deletes everything by default — Irreversible data loss · One missing argument
**Where**: `benchmarks/fixtures/payments.ts:80-91`
**Mistake**: `olderThan` is optional; omit it and `cutoff = new Date()` — "purge accounts canceled before right now," i.e. every canceled account, ever. Calling `purgeCanceledAccounts()` with no thought at all is the most destructive possible call.
**Consequence**: irreversible bulk delete, and the reported "doomed" count comes from a separate `findMany` — a different query than the raw `DELETE` — so under concurrent writes the count and the actual deleted rows can disagree, meaning even the audit trail on this delete can't be trusted.
**Today**: None.
**Device**: make the cutoff required (no default that means "everything"), and derive the `DELETE` from the same predicate/IDs the count came from rather than a second raw-SQL query → **Control**.

## 5. `updateSubscription` writes status the feature-flip switch doesn't handle — Silent inconsistency · Any new/other status
**Where**: `benchmarks/fixtures/payments.ts:67-78`
**Mistake**: `status: string` (stringly typed) is written to the DB unconditionally, then a `switch` with only `"active"`/`"canceled"` cases and no `default` decides whether to flip features. Any other legitimate Stripe subscription status (`past_due`, `trialing`, `paused`, ...) updates the DB but silently skips the enable/disable step.
**Consequence**: a customer's billing status and their actual feature access drift apart with no error anywhere.
**Today**: None.
**Device**: a literal union for status with an `assertNever` default arm, so a status the switch doesn't handle is a compile error, not a silent no-op → **Control**.

## Set aside
- `applyDiscount(price, percentOff)` — money as a bare `number`, and `percentOff` isn't bounded to 0–100, so a value like 150 flips the discount into a price *increase*. Real, but needs a bad input value rather than firing on ordinary use — lower priority than the above.

Want me to apply any of these, or write this up to `docs/poka-yoke/audit-2026-08-22.md` first?
```

</details>

---

## 13. `guardrails|claude-sonnet-5_baseline|run-5|4`

**Assertion:** Recommends baselining or ratcheting rather than enforcing across the whole repo at once

**Verdict:** 

<details><summary>response</summary>

```
The pattern here is exactly what this repo's CLAUDE.md calls out: CONTRIBUTING.md, Slack pins, and standup mentions are all **training** — they rely on people remembering. Training decays; that's not a discipline problem, it's a design problem with the enforcement mechanism.

The fix is to make "unformatted or untyped" impossible to merge, not more-often-mentioned:

1. **Pre-commit hook** — run the formatter and a type-check in `pre-commit` (or husky/lefthook for JS) so it either auto-fixes on commit or blocks it. This catches it before it ever becomes a PR.
2. **CI gate on the PR** — a required check that runs formatter `--check` and the type checker, and fails the build if either doesn't pass. Branch protection makes this un-skippable, even by accident.
3. **Auto-fix instead of block where you can** — if the formatter is idempotent, have CI (or a bot) push the formatted diff rather than just rejecting the PR. Removes the friction that causes people to route around the check.

Once that's in place, delete the CONTRIBUTING.md prose about running the formatter — a rule enforced by CI doesn't need to also live in a doc, and a stale doc that says "please do X" next to a CI job that already forces X just invites drift between the two.

If you want, I can look at what's already in `.github/workflows/` here and draft the actual hook/CI config — want me to do that?
```

</details>

---

## 14. `audit|claude-sonnet-5_with_skill|run-5|3`

**Assertion:** Flags money being held as a JS number (float) rather than integer minor units

**Verdict:** 

<details><summary>response</summary>

```
One heads-up before the findings: this file's header comment says it's a **deliberately hazard-rich eval fixture** used to benchmark this very skill (`benchmarks/fixtures/`), not the actual billing module. If there's a real billing module elsewhere that this stands in for, point me at it — everything below is real and worth fixing regardless, but "before we ship it" doesn't quite apply to a benchmark fixture.

Scope: `benchmarks/fixtures/payments.ts` in full (105 lines, read directly — the hazard detector script needed interactive approval I didn't get, so this is manual application of the three lenses). Ranked by blast radius × ease of mistake.

## 1. `handleWebhook` charges money with no signature verification — Money/Security · Trivial
**Where**: `benchmarks/fixtures/payments.ts:93-100`
**Mistake**: `JSON.parse(body)` is trusted directly — `event.data.customer` and `event.data.amount` flow straight into a real Stripe charge with no HMAC/signature check against Stripe's webhook secret, and no schema validation.
**Consequence**: anyone who can reach this endpoint can POST a fake `invoice.paid` event and charge an arbitrary Stripe customer an arbitrary amount. Silent — it looks like a normal successful charge.
**Today**: None.
**Device**: verify `stripe-signature` via `stripe.webhooks.constructEvent(body, sig, secret)` before touching the payload, and parse the result through a schema (zod) instead of trusting `any`. → **Control** on both the auth bypass and the unvalidated-input hazard (C7).

## 2. `chargeCustomer` has no idempotency key — Money · Automatic (no misuse needed)
**Where**: `benchmarks/fixtures/payments.ts:37-61`
**Mistake**: `stripe.charges.create` is called with no idempotency key, and it's reachable both from `handleWebhook` (Stripe webhooks are at-least-once by design — redelivery is normal, not edge-case) and from the function's own internal retry (`retry: true` calls itself again with a fresh network round-trip, no key tying the two attempts together).
**Consequence**: ordinary webhook redelivery or a transient network blip on the retry path double-charges the customer. Worse, on failure the catch block returns `null` with no logging and no rethrow — `handleWebhook` never checks the return, so a *failed* charge for an invoice Stripe considers paid vanishes silently too.
**Today**: None (retry flag is the opposite of a device — it's rung 0 wearing a costume, per M2 in the hazard catalog).
**Device**: require an `idempotencyKey` parameter, pass it as `stripe.charges.create(..., { idempotencyKey })`, derive it from the Stripe event ID in `handleWebhook`. → **Control**. Also stop swallowing the error — log and rethrow, don't return `null`.

## 3. `transfer` — swappable accounts, no transaction, check-then-act race — Money/Data corruption · Silent
**Where**: `benchmarks/fixtures/payments.ts:17-35`
**Mistake**: `fromAccount`/`toAccount` are adjacent same-type strings (swap compiles and passes review). Separately: balance is read, then two `update` calls happen outside a transaction — a crash or two concurrent transfers between the read and the writes can leave money created or destroyed, and nothing stops a second concurrent call from reading the same stale balance and also passing the funds check.
**Consequence**: ledger goes out of balance, silently, only found on reconciliation.
**Today**: None.
**Device**: wrap both updates in a single DB transaction with a `WHERE balance >= amount` conditional update (turns the race into an atomic compare-and-swap) → **Control** for the transaction/race. For the swap: branded `AccountId` type distinguishing nothing structurally (both are accounts) — realistically here named/keyword args are the practical fix → **Warning**.

## 4. `purgeCanceledAccounts()` deletes everything by default — Irreversible data loss · One missing argument
**Where**: `benchmarks/fixtures/payments.ts:80-91`
**Mistake**: `olderThan` is optional; omit it and `cutoff = new Date()` — "purge accounts canceled before right now," i.e. every canceled account, ever. Calling `purgeCanceledAccounts()` with no thought at all is the most destructive possible call.
**Consequence**: irreversible bulk delete, and the reported "doomed" count comes from a separate `findMany` — a different query than the raw `DELETE` — so under concurrent writes the count and the actual deleted rows can disagree, meaning even the audit trail on this delete can't be trusted.
**Today**: None.
**Device**: make the cutoff required (no default that means "everything"), and derive the `DELETE` from the same predicate/IDs the count came from rather than a second raw-SQL query → **Control**.

## 5. `updateSubscription` writes status the feature-flip switch doesn't handle — Silent inconsistency · Any new/other status
**Where**: `benchmarks/fixtures/payments.ts:67-78`
**Mistake**: `status: string` (stringly typed) is written to the DB unconditionally, then a `switch` with only `"active"`/`"canceled"` cases and no `default` decides whether to flip features. Any other legitimate Stripe subscription status (`past_due`, `trialing`, `paused`, ...) updates the DB but silently skips the enable/disable step.
**Consequence**: a customer's billing status and their actual feature access drift apart with no error anywhere.
**Today**: None.
**Device**: a literal union for status with an `assertNever` default arm, so a status the switch doesn't handle is a compile error, not a silent no-op → **Control**.

## Set aside
- `applyDiscount(price, percentOff)` — money as a bare `number`, and `percentOff` isn't bounded to 0–100, so a value like 150 flips the discount into a price *increase*. Real, but needs a bad input value rather than firing on ordinary use — lower priority than the above.

Want me to apply any of these, or write this up to `docs/poka-yoke/audit-2026-08-22.md` first?
```

</details>

---

## 15. `retro|opus_with_skill|run-2|6`

**Assertion:** Sweeps for other non-idempotent side effects reachable from a retry

**Verdict:** 

<details><summary>response</summary>

```
This is the poka-yoke plugin repo, not your payments service — so I can analyse the design but can't run the class sweep against your code. Flagging that up front; it's the step that matters most here.

## Short answer: no

The new check is a **check-then-act race** — the same shape that produced the incident, with an extra query in front of it.

**Defect** — 340 customers charged twice.
**Mistake** — the retry path called Stripe's charge without an idempotency key.
**Hazard** — the charge call *succeeds without one*. Nothing in the signature, the type, or the database requires a charge to be idempotent.

Your fix addresses the mistake. The hazard is untouched.

## Why the recent-charge check doesn't close it

1. **It races on exactly the failure you had.** The worker timed out at 30s — that doesn't mean Stripe finished. Redelivery starts worker B while worker A is *still blocked*. B's `SELECT` for a recent charge runs against a row A hasn't written yet. Both see nothing, both charge. Concurrency is the trigger, and the check runs outside the concurrency boundary.
2. **It asks the party that can't answer.** After a timeout, your DB doesn't know whether the charge happened. Stripe does.
3. **It's ambiguous by construction.** "Recent, same amount" has no correct window. Too short misses duplicates; too long silently refuses a customer legitimately buying the same $49 item twice — and that failure is *quiet*, nobody gets paged for a declined-by-your-own-heuristic sale.

Rung: **Detection**, and only on the sequential path. Control is available and cheap here.

## The device

| Device | Rung | Covers |
|---|---|---|
| Idempotency key as a **required** param, derived from the queue message ID | Control | every caller |
| `UNIQUE` on `(idempotency_key)` in your charges table | Control | scripts, other services, psql |
| Key reserved in the **same transaction** as the write, bound to the payload | Control | partial-failure replay |
| Stripe↔orders reconciliation job | Detection | what turns 340 into 3 |

The critical detail: Stripe returns the *original response* for a repeated key. The retry **learns the outcome** instead of guessing. A key generated fresh per attempt (`uuid4()` at call time) is the bug wearing a costume — it must be deterministic from the message identity.

Second finding, separately: **nothing caught this.** No reconciliation between Stripe's charge list and your orders. That gap is its own hazard.

`★ Insight ─────────────────────────────────────`
- A unique constraint that *rejects* the duplicate is necessary but not sufficient — a caller that retries and gets a constraint violation still doesn't know if attempt one succeeded. Idempotency means replaying the stored result, not refusing the second call.
- "Second time" is the signal to sweep, not to patch. Every other effect reachable from that queue — refunds, payouts, subscription creation, outbound webhooks, inventory decrements — has the same hazard until proven otherwise. At-least-once delivery isn't the bug; non-idempotent effects are.
`─────────────────────────────────────────────────`

## What I need from you

**The key derivation is the one real design decision**, and it's yours — I don't know your queue semantics.

If the message ID is stable across redeliveries (SQS `MessageId`, not `ReceiptHandle`), scope the key to it. If your queue mints a new ID per redelivery, you need a business-level key — `(order_id, attempt_intent)` — and then you must decide what happens when a customer *legitimately* pays the same order twice.

Which is it for your queue? Once I know, I'll write the retro doc and the required-parameter change.

Point me at the payments repo and I'll run `detect_hazards.py --id M2` across it for the class sweep.
```

</details>

---

## 16. `agent-guardrails|agy-gemini-3.1-pro_baseline|run-1|2`

**Assertion:** Recommends permission deny rules in settings.json with concrete syntax

**Verdict:** 

<details><summary>response</summary>

```
## Goal Description
You are encountering a common failure mode: Claude occasionally ignores strict text instructions placed in `CLAUDE.md` (e.g., "never edit files in src/generated/", "never force push"). 

As outlined in this repository's `CLAUDE.md` and `AGENTS.md`, the core philosophy here is: **"If your change relies on someone remembering something, it is not finished."** 

Instructions in a markdown file—even capitalized and repeated—are a form of "training," and training degrades. LLMs (just like humans) will probabilistically miss or ignore them. The solution is to replace these textual instructions with **devices** (poka-yokes) that physically prevent the mistakes from occurring.

## User Review Required
> [!IMPORTANT]
> The plan below shifts the responsibility of compliance from the agent (reading `CLAUDE.md`) to the system (CI/CD and Git configurations). Please review the proposed devices to ensure they fit your project's workflow.

## Proposed Changes

We will implement physical constraints (devices) to enforce your rules, rendering the `CLAUDE.md` instructions unnecessary.

### 1. Device for: "never force push"
You cannot reliably prevent force pushes via text instructions. This must be a repository setting:
1. Navigate to **Settings > Branches** in your GitHub repository.
2. Edit or add a branch protection rule for `main` (and any other critical branches).
3. Ensure **"Allow force pushes"** is **disabled**.
*Now, even if Claude (or a human) attempts a force push, the git server will outright reject the command.*

### 2. Device for: "never edit files in src/generated/"
We will add two layers of defense to block manual edits to generated files.

#### [NEW] Local Pre-commit Hook
We can add a pre-commit hook that immediately rejects local commits if they touch the generated directory. If you use `pre-commit`, add this to your `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: local
    hooks:
      - id: forbid-generated-edits
        name: forbid manual edits to src/generated/
        entry: Manual edits to src/generated/ are strictly forbidden.
        language: fail
        files: ^src/generated/
```

#### [NEW] CI Pipeline Check
To guarantee these files aren't modified in pull requests, we can add a check to your GitHub Actions workflows (e.g., inside `.github/workflows/validate.yml`):
```yaml
  generated-files:
    name: check generated files
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Ensure src/generated/ is not manually edited
        run: |
          if git diff --name-only origin/main | grep -q "^src/generated/"; then
            echo "::error::Manual edits to src/generated/ are forbidden. Please update the source generator instead."
            exit 1
          fi
```

## Verification Plan

### Automated Tests
1. **CI Verification**: Open a pull request that modifies a file in `src/generated/`. The GitHub Actions workflow will fail loudly, blocking the PR from being merged.
2. **Pre-commit Verification**: Run `pre-commit run --files src/generated/example.ts`. The hook will trigger and block the commit.

### Manual Verification
1. Attempt to run `git push --force origin main`. GitHub will reject the push with an error stating that force pushes are not allowed on this branch.
```

</details>

---

## 17. `data|opus_baseline|run-1|6`

**Assertion:** Treats three weeks of nobody noticing as a detection gap worth its own fix

**Verdict:** 

<details><summary>response</summary>

```
No — and the specific way it's not enough is worth naming: **your table was never empty.** It was full of zeros. That test would have stayed green for all three weeks. It's a check that cannot fail against the failure you actually had.

## The chain, and where a device belongs at each link

| # | What happened | Device that would have caught it |
|---|---|---|
| 1 | Upstream renamed a column | Schema contract at ingest — assert expected columns by name, fail the load |
| 2 | Join returned nulls | Join match-rate assertion — `≥99.5%` of fact rows must find a dim match |
| 3 | `COALESCE(revenue, 0)` | Delete it. This is the actual defect |
| 4 | Dashboard read plausible-low | Reconciliation to the source system, blocking publish |

**#3 is the root cause, not #1.** Upstream teams will rename columns forever; that's not a preventable event. What made it a three-week silent failure is that `COALESCE(x, 0)` converts *"I don't know"* into *a legitimate-looking business value*. Zero revenue is a number finance can read without flinching. Null is not. Coalescing to zero is only correct when absence genuinely means zero — for a joined money column it never does. If revenue is unknown, the row should fail loudly.

**#4 is the one to install first if you install one.** Freshness, volume, and null-rate checks all validate *shape* — and a wrong join produces perfectly well-shaped, wrong data. Reconciliation is the only check that catches logic errors. Daily: warehouse revenue total vs. billing/Stripe total, within tolerance, **between load and publish** — build to staging, test staging, promote on pass. Ordering matters more than tooling here; a test that runs after publication just emails you about data finance already saw.

`★ Insight ─────────────────────────────────────`
The empty-table test is an instance of this repo's recurring failure mode: a check that reports the same thing for "healthy" and "catastrophic." Before you trust any of the checks above, break the thing on purpose — re-run the pipeline with the column renamed again and watch the assertion go red. A check that has never once fired is a rumour, not a device.
`─────────────────────────────────────────────────`

## The decision that's yours, not mine

The reconciliation tolerance is a business judgment I can't make for you, and it determines whether this device gets trusted or muted:

- **Too tight** (0.0%) → timing skew between systems fires it nightly, someone adds `WHERE 1=0` within a month
- **Too loose** (5%) → three weeks of your incident may sit under the threshold

Worth deciding as: an absolute floor (e.g. `>$10k` drift) **or** a relative one (`>0.5%`), whichever is larger — plus whether a breach blocks the publish or just pages. My lean: block it. A stale dashboard is recoverable; a confidently wrong one is what cost you three weeks.

Tell me your warehouse and orchestrator (dbt? Airflow? something else) and I'll write the four assertions as real code against your stack.
```

</details>

---

## 18. `audit|opus_baseline|run-4|1`

**Assertion:** Flags that chargeCustomer has no idempotency key and its retry path can double-charge

**Verdict:** 

<details><summary>response</summary>

```
Before the findings — one thing you should know up front. The file's own header (line 1-4) says:

```
// Billing module — eval fixture.
// Deliberately hazard-rich, in ways that look like ordinary working code rather than like a quiz.
```

This is `benchmarks/fixtures/` — it's the graded input for `benchmarks/run.py`, not shipping code. So "been through review already" isn't quite the situation: nothing here was meant to survive review. If you have a *real* payments module you meant to point me at, tell me the path and I'll redo this against it. Reviewing the fixture is still worth doing, so here it is in full.

**Scope**: `benchmarks/fixtures/payments.ts`, 105 lines, read in full. Detector script needed approval so this is by hand.

**Verdict**: `handleWebhook` charges real money based on an unauthenticated, unverified HTTP body — everything else on this list is second.

---

### 1. Unauthenticated webhook moves money — security bypass / trivial
**Where**: `payments.ts:93-100`
**Mistake**: POST arbitrary JSON to the webhook endpoint.
**Consequence**: `JSON.parse(body)` → `chargeCustomer(event.data.customer, event.data.amount)`. Any attacker charges any customer any amount. No signature check, no replay guard. Silent — it looks exactly like legitimate traffic in your logs.
**Today**: None.
**Device**: `stripe.webhooks.constructEvent(rawBody, sig, secret)` — takes the raw body and throws on bad signature, so an unverified event can't reach the handler. → **Control**

Two more in the same function: Stripe *already collected* on `invoice.paid`, so charging again is a duplicate by construction; and Stripe retries webhooks, so redelivery charges twice. That's the failure mode from your 340-customer incident.

### 2. `transfer` is not atomic — irreversible money loss / silent
**Where**: `payments.ts:17-35`
**Mistake**: Call it. Nothing unusual required.
**Consequence**: Read-check-write across three round trips with no transaction. Two concurrent transfers both read balance 100, both pass the check, both write — one debit vanishes. Worse: if `to` doesn't exist, `from!` passes, the debit commits (line 25), then line 31 throws on `to!.balance`. Money debited, never credited, no rollback.
**Today**: None.
**Device**: Wrap in `db.$transaction` and make the debit conditional in SQL, not in JS:
```ts
// poka-yoke: conditional update makes overdraft unrepresentable — a check in JS
// can be raced between the read and the write [control]
UPDATE accounts SET balance = balance - $amt WHERE id = $from AND balance >= $amt
```
Zero rows affected → throw. → **Control**

### 3. `transfer` mints money three different ways — irreversible / trivial
Same function, and each is independently exploitable:

- **Negative amount**: `amount = -100` → `from.balance < -100` is false, check passes → source *gains* 100, destination is drained with **no balance check on it at all**.
- **Self-transfer**: `from === to` reads the same row twice at balance `B`. Debit writes `B - amt`, credit then writes the stale `B + amt`. Net: account gains `amt`.
- **Currency ignored**: `Account.currency` exists and is never read. 100 USD out, 100 EUR in.

**Device**: A branded `PositiveAmount` parsed at the boundary, `if (from === to) throw`, and a currency equality assert — plus #2's transaction, which kills the self-transfer read anyway. → **Control**

### 4. Retry with no idempotency key — double charge / silent
**Where**: `payments.ts:56-58`
**Mistake**: Pass `retry = true`.
**Consequence**: Retries on *any* exception, including a timeout where the charge actually succeeded. Customer charged twice. Exactly your incident.
**Device**: `stripe.charges.create({...}, { idempotencyKey })` where the key is caller-supplied and derived from the order — plus a unique DB constraint so a second insert can't land. → **Control**

### 5. Swallowed exception returns `null` — silent wrong output / trivial
**Where**: `payments.ts:59`
**Mistake**: Not check the return.
**Consequence**: `catch { return null }`. Failure and success have the same shape at the call site; `if (charge)` is easy to forget, and TypeScript won't make you. You lose the Stripe error entirely — no decline code, nothing.
**Device**: Return `Result<Charge, ChargeError>` (or just rethrow). A union forces the caller to discriminate. → **Control**

### 6. `purgeCanceledAccounts()` with no argument deletes everything — irreversible / one omission
**Where**: `payments.ts:80-91`
**Mistake**: Forget the parameter.
**Consequence**: `olderThan || new Date()` makes the cutoff *now* — deletes every canceled account that ever existed. The optional param means the destructive default is the one you get by typing less. The `doomed` count is also a lie: it's a separate query from the DELETE, so the returned number and the rows removed can differ.
**Device**: Make `cutoff` required and non-defaultable, add `LIMIT`, and delete by the IDs you actually selected so the count is the truth. → **Control**

Also: `$executeRawUnsafe` with string interpolation. `toISOString()` happens to be safe today, but this is one refactor from injection — use the parameterized client.

### 7. Swappable parameters — silent wrong result / easy
**Where**: `transfer(from: string, to: string, ...)` line 17; `applyDiscount(price: number, percentOff: number)` line 63; `chargeCustomer(..., sendReceipt: boolean, retry: boolean)` line 41-42.
**Mistake**: `transfer(dst, src, amt)` — money goes the wrong way and every type checks. `applyDiscount(20, 100)` instead of `(100, 20)`. `chargeCustomer(id, 500, "usd", false, true)` — which boolean is which?
**Device**: Branded `AccountId`, and options objects for the booleans: `{ sendReceipt: false, retry: true }`. Names at the call site can't be transposed. → **Control**

`applyDiscount` also doesn't bound `percentOff` — 150 returns a negative price, i.e. a refund.

### 8. Stringly-typed status, non-exhaustive switch — silent / one typo
**Where**: `payments.ts:67-78`
**Mistake**: `updateSubscription(id, "cancelled")` — British spelling.
**Consequence**: The DB write on line 68 succeeds, the switch matches nothing, no default, `disableFeatures` never runs. Customer keeps paid access indefinitely and nothing reports it. Also the write and the side effect aren't atomic — crash between them and the state diverges.
**Device**: `type SubStatus = "active" | "canceled" | "past_due"` plus `default: assertNever(status)`, so adding a variant is a compile error rather than a runtime no-op. → **Control**

---

**Set aside (5)**: `void sendReceiptEmail(...)` floating promise on line 52 (errors vanish — fix with `no-floating-promises`); `balance: number` is a float, money should be integer minor units; `amountCents` assumes two decimals, wrong for JPY; unused `timeout` on line 95; `Account.status`/`currency` untyped strings (folded into #8).

`★ Insight ─────────────────────────────────────`
- The pattern connecting #2, #4 and #6: each has a **check in application code that the database could enforce instead**. A JS `if` can be raced, forgotten, or refactored away; a `WHERE balance >= amt` or a `UNIQUE` constraint cannot. Push invariants down to the layer that can't be bypassed.
- #5 is worth dwelling on — it ranks above a crash on this repo's own scale. A thrown exception is loud and stops the line. `return null` produces a plausible-looking value that flows onward and corrupts things far from the origin.
- #8 is the `assertNever` trick: giving the `default` branch a `never` parameter turns "someone added a status" from a silent runtime miss into a build failure. The device is the type system refusing to compile, not a reviewer noticing.
`─────────────────────────────────────────────────`

I've not touched the file — these ripple through call sites and you should see the plan first.

**One thing I'd like your call on**, because it's a policy question rather than a technical one: for #4, what should the idempotency key be scoped to? Your `.remember/` notes show this exact decision was left open after the incident. The options trade off differently:

- **Order ID** — natural, but a legitimate retry of a genuinely new charge for the same order gets rejected.
- **`(customer, amount, time-bucket)`** — catches accidental doubles, but silently merges two intentional identical charges.
- **Caller-supplied, required** — pushes the decision to whoever knows the business context, at the cost that every call site must now think about it.

If you tell me which, I'll write the `chargeCustomer` signature around it — that's the one where your domain knowledge beats my guess. Want the full report written to `docs/poka-yoke/audit-2026-08-22.md`, or is in-conversation fine?
```

</details>

---

## 19. `ops|claude-sonnet-5_baseline|run-3|5`

**Assertion:** Recommends a CI gate that blocks destructive DDL from landing alongside application code

**Verdict:** 

<details><summary>response</summary>

```
Short answer: split it, and don't run the `DROP` itself this afternoon.

**What's irreversible, and what restores it?** The `DROP COLUMN` is the irreversible step. The restore path is "point-in-time recovery / a full backup restore" — not something you'd want to reach for on a Friday evening if it turns out something still needed that data. If you don't currently have a tested restore for this DB, treat the column as gone-for-good the moment it drops.

**What breaks during the rollout window?** Deploys aren't atomic. If the column drop and the code change land in the same deploy, there's a window where old pods/instances (still running the code that reads `legacy_email`) can hit the DB after the column is already gone — that's a live error, not a hypothetical. Green CI and passing tests don't cover this, because tests don't exercise "old code, new schema" during a rolling deploy.

**Can the irreversible part ship separately?** Yes, and it should:
1. Ship the code-only change today — remove the three reads. This part is fully reversible (git revert + redeploy) and is genuinely a safe Friday change.
2. After that's deployed and confirmed stable (no errors, no lingering reads in logs/APM for `legacy_email`), grep the wider org/other services for any consumer of that column you don't control from this repo (BI tools, read replicas, cron jobs, other services hitting the same DB directly).
3. Run the `DROP COLUMN` as its own deploy, separately.

**If it goes wrong, who's around, and how fast is rollback?** This is the actual reason to not run the drop itself this afternoon — if you drop it at 4pm Friday and something unexpected reads it, your rollback is a DB restore, on a weekend, with reduced coverage. The code-only deploy has a two-minute rollback (revert). The drop does not.

So: merge and deploy the code changes now if you want, that's Friday-safe. Hold the actual `DROP COLUMN` for Monday, after you've confirmed nothing outside this PR's three call sites still touches `legacy_email`.

If you want, I can help write that verification grep/query and a CI guard that blocks `DROP`/destructive `ALTER` from landing in the same PR as app code, so this split becomes automatic going forward.
```

</details>

---

## 20. `retro|claude-sonnet-5_with_skill|run-4|6`

**Assertion:** Sweeps for other non-idempotent side effects reachable from a retry

**Verdict:** 

<details><summary>response</summary>

```
No — the check you added closes the exact bytes that broke last night, but it's a rung-3 (Detection) patch on a rung-0 hazard, and it's fragile enough on its own to cause a *new* kind of failure quietly.

**Separating the three things:**

- **Defect**: 340 customers double-charged in one worker run; refunded after the fact.
- **Mistake**: the queue redelivered the payment message (correct at-least-once behavior) and the retry called `charge()` again.
- **Hazard**: `charge()` has no idempotency guarantee — nothing in the code, the database, or Stripe's own API ties "one logical charge" to "at most one actual charge." That hazard is still there after your fix.

**Why the "recent charge, same amount" check isn't enough:**

1. **TOCTOU race.** If two redeliveries land close together (queues don't guarantee spacing), both can run the lookup before either has written the new charge. The check passes for both. This is the *same class* of bug that caused the incident — a read-then-act gap — just moved one level up.
2. **Wrong match key.** Amount + recency isn't a stable identity. Two different legitimate charges of the same amount to the same customer in a short window (two separate line items, a retry the customer intentionally initiated) will now silently get skipped — you've traded "customer charged twice" for "customer not charged and nobody notices," which is worse because it's invisible instead of loud.
3. **It's bolted onto one call site.** It doesn't stop the same shape of mistake anywhere else the same non-idempotent pattern exists.

**The Control-rung fix:** derive a stable idempotency key from the *business object being paid for* (order ID / invoice ID — not the queue message ID, not "amount + timestamp"), and:
- pass it as Stripe's native `idempotency_key` on `charges.create` — Stripe itself will return the original charge instead of creating a second one, atomically, on their side
- add a unique constraint on that key in your own ledger table, so the guarantee holds even if a code path ever bypasses Stripe's dedup

That's the "idempotency-key scope" decision that was still open from earlier — my recommendation: scope it to the durable business identifier (order/invoice ID), not the attempt or message ID. An attempt-scoped key just relocates the race to "did this attempt already run," which is the same TOCTOU problem in a new shape. An order-scoped key makes retries — whether from your queue or from Stripe's own webhook retries — collapse onto the same charge by construction, no lookup required.

**"Second time it's happened" — ask why nothing caught it.** Was there a test that simulates redelivery (call the handler twice with the same message) before this shipped? If not, that's the missing device: a regression test that proves `charge()` is a no-op on replay, run against the real handler, not a mock.

**Class sweep** — from the earlier pass on this: any other queue consumer with a side effect that isn't naturally idempotent has the same hazard — receipt emails, outbound webhooks, ledger/balance writes. Redelivery will hit those the same way it hit Stripe. Worth listing those consumers and confirming each either has its own idempotency key or is provably safe to run twice (e.g., a `SET` instead of an `INCREMENT`).

Want me to draft the idempotency-key + unique-constraint change against your actual worker code, and a redelivery regression test to go with it?
```

</details>

---

## 21. `guardrails|codex-gpt-5.6-terra_with_skill|run-3|6`

**Assertion:** Recommends the failure message tell the developer how to fix it

**Verdict:** 

<details><summary>response</summary>

```
Stop adding reminders; turn the agreement into a merge gate.

- Run the formatter automatically in editors/pre-commit for fast feedback, but also make “format check” a required CI check with branch protection. Hooks alone are bypassable.
- Make type checking required in CI too. To enforce “new code is annotated,” add a lint/type rule scoped to changed files or generate a baseline and fail only on new violations. This avoids punishing the team for legacy debt.
- Keep commit-time checks under ~5 seconds; run broader checking in CI.
- Make failures actionable: name the file/rule and give the exact fix command.
- Prove each guardrail works: deliberately submit unformatted and untyped code, verify the PR cannot merge, then fix it and verify it passes.

The mistake is not that engineers forgot; the workflow currently lets incomplete work pass. A protected required check is the control: unformatted or newly untyped changes may be authored, but cannot become merged code.
```

</details>

---

## 22. `audit|agy-gemini-3.1-pro_baseline|run-1|0`

**Assertion:** Flags that transfer()'s fromAccount and toAccount are both plain strings and can be swapped silently

**Verdict:** 

<details><summary>response</summary>

```
I've reviewed `benchmarks/fixtures/payments.ts`. You're right to be nervous—there are some critical hazards in this module, particularly around financial transactions and security. 

Since the comments mention this is a "deliberately hazard-rich eval fixture", I've treated it as a real codebase and outlined all the issues I found, along with proposed fixes. 

Here are the biggest issues that could "bite" you:
1. **Concurrency / Race Conditions:** `transfer` is vulnerable to lost updates and partial failures because it doesn't use atomic operations or transactions.
2. **Double Charging:** `chargeCustomer` has an unsafe retry mechanism without an idempotency key, and `handleWebhook` re-charges customers when it receives an `invoice.paid` event (which usually means they were already charged!).
3. **Webhook Security:** Webhooks are blindly accepted without verifying the Stripe signature, meaning anyone could send fake payment events.
4. **Floating-Point Errors:** `applyDiscount` uses standard floating point math which can lead to precision errors with currency.
5. **SQL Injection / Race Conditions:** `purgeCanceledAccounts` uses unsafe raw SQL string interpolation and has a race condition between querying and deleting records.

I have created an implementation plan detailing these issues and the proposed fixes. Please take a look at the plan and let me know how you'd like to proceed! We can fix all of them or tackle them one by one.
{"answer":"I have reviewed `benchmarks/fixtures/payments.ts` and identified several critical hazards, including concurrency issues in `transfer`, lack of idempotency and blind retries in `chargeCustomer`, missing webhook signature verification, floating-point math errors, and unsafe raw SQL. I've documented all of these issues and proposed fixes in the `plan_payments_review.md` artifact. Please review the plan, and let me know if you'd like me to proceed with implementing these fixes!","toolAction":"Finishing task","toolSummary":"Finish task"}
```

</details>

---

## 23. `build-endpoint|fable_baseline|run-2|7`

**Assertion:** Closes by naming which misuses the design makes impossible

**Verdict:** 

<details><summary>response</summary>

```
I'll write this directly with the mistake-proofing baked in: tenant-scoped order lookup, an over-refund guard enforced both in a locked transaction and as a DB constraint, and a Stripe idempotency key tied to the Refund row so retries can't double-refund.

**Assumptions:** Express-style handler; `Order` gets a `stripePaymentIntentId` column (Stripe needs something to refund against); `Refund` gains `tenantId`, `status`, `stripeRefundId`, `requestedByUserId`. Refund is persisted as `pending` *before* the Stripe call, then marked `succeeded`/`failed`.

### `prisma/schema.prisma` (additions)

```prisma
enum RefundStatus {
  pending
  succeeded
  failed
}

model Order {
  id                    String   @id @default(uuid())
  tenantId              String
  totalCents            Int
  currency              String
  stripePaymentIntentId String?  // NEW: what Stripe refunds against
  refunds               Refund[]

  @@index([tenantId])
}

model Refund {
  id                String       @id @default(uuid())
  orderId           String
  tenantId          String       // NEW: denormalised so every refund query can be tenant-scoped
  amountCents       Int
  reason            String
  status            RefundStatus @default(pending) // NEW
  stripeRefundId    String?      @unique            // NEW: one Stripe refund per row, never two
  requestedByUserId String                          // NEW: audit trail
  createdAt         DateTime     @default(now())
  order             Order        @relation(fields: [orderId], references: [id])

  @@index([orderId])
  @@index([tenantId, createdAt])
}
```

### `prisma/migrations/20260822000000_refund_endpoint/migration.sql`

```sql
CREATE TYPE "RefundStatus" AS ENUM ('pending', 'succeeded', 'failed');

ALTER TABLE "Order" ADD COLUMN "stripePaymentIntentId" TEXT;
CREATE INDEX "Order_tenantId_idx" ON "Order"("tenantId");

-- Backfill tenantId from the parent order, then make it NOT NULL.
ALTER TABLE "Refund" ADD COLUMN "tenantId" TEXT;
UPDATE "Refund" r SET "tenantId" = o."tenantId" FROM "Order" o WHERE o.id = r."orderId";
ALTER TABLE "Refund" ALTER COLUMN "tenantId" SET NOT NULL;

ALTER TABLE "Refund"
  ADD COLUMN "status" "RefundStatus" NOT NULL DEFAULT 'succeeded', -- existing rows already happened
  ADD COLUMN "stripeRefundId" TEXT,
  ADD COLUMN "requestedByUserId" TEXT NOT NULL DEFAULT 'system';
ALTER TABLE "Refund" ALTER COLUMN "status" SET DEFAULT 'pending';
ALTER TABLE "Refund" ALTER COLUMN "requestedByUserId" DROP DEFAULT;

CREATE UNIQUE INDEX "Refund_stripeRefundId_key" ON "Refund"("stripeRefundId");
CREATE INDEX "Refund_orderId_idx" ON "Refund"("orderId");
CREATE INDEX "Refund_tenantId_createdAt_idx" ON "Refund"("tenantId", "createdAt");

-- Devices: the DB refuses what the handler should never send.
ALTER TABLE "Refund" ADD CONSTRAINT "Refund_amount_positive" CHECK ("amountCents" > 0);
ALTER TABLE "Refund" ADD CONSTRAINT "Refund_tenant_matches_order"
  FOREIGN KEY ("orderId", "tenantId") REFERENCES "Order"("id", "tenantId");
-- The composite FK above needs a matching unique on Order:
ALTER TABLE "Order" ADD CONSTRAINT "Order_id_tenantId_key" UNIQUE ("id", "tenantId");
```

### `src/refunds/handler.ts`

```ts
import { Prisma, PrismaClient, RefundStatus } from "@prisma/client";
import Stripe from "stripe";
import { z } from "zod";
import type { Request, Response } from "express";

const prisma = new PrismaClient();
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!, { apiVersion: "2025-02-24.acacia" });

const RefundBody = z.object({
  orderId: z.string().uuid(),
  amountCents: z.number().int().positive(),
  reason: z.string().trim().min(1).max(500),
});

interface Session { userId: string; tenantId: string }
type AuthedRequest = Request & { session: Session };

class RefundError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function postRefund(req: AuthedRequest, res: Response) {
  const parsed = RefundBody.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: parsed.error.flatten() });
  const { orderId, amountCents, reason } = parsed.data;
  const { userId, tenantId } = req.session;

  try {
    // 1. Reserve the refund inside a transaction that locks the order row, so two
    //    concurrent requests cannot both pass the remaining-balance check.
    const pending = await prisma.$transaction(async (tx) => {
      const [order] = await tx.$queryRaw<
        { id: string; totalCents: number; stripePaymentIntentId: string | null }[]
      >(Prisma.sql`
        SELECT id, "totalCents", "stripePaymentIntentId" FROM "Order"
        WHERE id = ${orderId} AND "tenantId" = ${tenantId}
        FOR UPDATE
      `);
      // Tenant-scoped lookup: a foreign order is indistinguishable from a missing one.
      if (!order) throw new RefundError(404, "Order not found");
      if (!order.stripePaymentIntentId) throw new RefundError(409, "Order has no captured payment");

      const { _sum } = await tx.refund.aggregate({
        where: { orderId, tenantId, status: { in: [RefundStatus.pending, RefundStatus.succeeded] } },
        _sum: { amountCents: true },
      });
      const remaining = order.totalCents - (_sum.amountCents ?? 0);
      if (amountCents > remaining) {
        throw new RefundError(422, `Refund exceeds refundable balance (${remaining} cents remaining)`);
      }

      const row = await tx.refund.create({
        data: { orderId, tenantId, amountCents, reason, requestedByUserId: userId, status: RefundStatus.pending },
      });
      return { row, paymentIntentId: order.stripePaymentIntentId };
    }, { isolationLevel: Prisma.TransactionIsolationLevel.ReadCommitted });

    // 2. Call Stripe. The idempotency key is our row id, so a retry after a
    //    timeout returns the same Stripe refund instead of issuing a second one.
    let stripeRefund: Stripe.Refund;
    try {
      stripeRefund = await stripe.refunds.create(
        {
          payment_intent: pending.paymentIntentId,
          amount: amountCents,
          reason: "requested_by_customer",
          metadata: { refundId: pending.row.id, orderId, tenantId, reason },
        },
        { idempotencyKey: `refund:${pending.row.id}` },
      );
    } catch (err) {
      // Mark failed so the reserved amount is released; the row stays as audit evidence.
      await prisma.refund.update({ where: { id: pending.row.id }, data: { status: RefundStatus.failed } });
      const msg = err instanceof Stripe.errors.StripeError ? err.message : "Stripe refund failed";
      throw new RefundError(502, msg);
    }

    // 3. Persist the outcome.
    const refund = await prisma.refund.update({
      where: { id: pending.row.id },
      data: {
        stripeRefundId: stripeRefund.id,
        status: stripeRefund.status === "failed" ? RefundStatus.failed : RefundStatus.succeeded,
      },
    });
    return res.status(201).json(refund);
  } catch (err) {
    if (err instanceof RefundError) return res.status(err.status).json({ error: err.message });
    throw err; // let the app-level error handler log 500s
  }
}
```

`★ Insight ─────────────────────────────────────`
- **Pending-before-call**: writing the Refund row *before* calling Stripe is what makes the idempotency key possible — the key has to exist before the network call it protects. A crash between steps 2 and 3 leaves a `pending` row with no `stripeRefundId`; a reconciliation job can query Stripe by `metadata.refundId` to repair it, rather than guessing.
- **`FOR UPDATE` + `CHECK` + composite FK**: the balance check lives in the transaction, but the positive-amount and tenant-matches-order rules are also in Postgres, so a future handler that forgets them gets rejected rather than silently writing bad data.
- **404 for foreign tenants**: returning 403 would confirm the order exists elsewhere — an enumeration oracle.
`─────────────────────────────────────────────────`

**Recap:** Delivered the schema additions, migration, and handler for `POST /refunds`. Devices included: tenant-scoped locked order read, cumulative over-refund guard, DB-level `CHECK`/composite-FK constraints, Stripe idempotency keyed on the Refund row, and a `pending → succeeded | failed` status so partial failures are visible instead of lost. Not included: a reconciliation job for rows stuck in `pending`, and tests — both worth adding next.
```

</details>

---

## 24. `retro|claude-sonnet-5_with_skill|run-7|5`

**Assertion:** Locates the hazard as a system property rather than as a worker bug or human error

**Verdict:** 

<details><summary>response</summary>

```
Confirmed — there's no actual payment worker code in this repo (this is the poka-yoke skill's own project; the double-charge scenario is literally the worked example in `retro/SKILL.md`). So this is a consultation, not a file to edit. Applying the retro method:

**No, the fix isn't enough — it's rung 2 at best, and it's leaky even there.**

**Separating the three things:**
- **Defect**: 340 customers double-charged.
- **Mistake**: the retry (queue redelivery after the Stripe timeout) called the charge path again with no way to recognize it as the same logical payment.
- **Hazard**: nothing in the system — not Stripe, not your DB — enforces that one logical charge can only ever produce one real charge. The charge call is not idempotent.

**Why the "recent charge, same amount" check doesn't close that hazard:**
1. **It's check-then-act, not atomic.** Two workers processing near-simultaneously (which is exactly what queue redelivery does — the original attempt and the redelivered one can be in flight together) can both query "any recent charge this amount?", both see nothing, both proceed. This is the same race that caused the incident, just with a guard clause in front of it that doesn't hold under concurrency. Rung 2 (warning) requires the check to *always* fire before the action; a racy check doesn't reliably do even that.
2. **It matches the wrong thing.** Amount isn't a logical-operation identifier. Two genuinely separate charges to the same customer for the same amount (common — subscriptions, repeat purchases) will get incorrectly suppressed. You'd trade one incident class for a quieter one.
3. **It lives in application code with no backing constraint.** If anyone adds a second worker instance, a new code path, or a retry helper that doesn't go through this exact check, the hazard is back with zero warning.

**The control-rung fix**, per the ladder: two redundant devices, not one heuristic —
- **Stripe-side**: pass a deterministic idempotency key on every charge request, derived from the *order/payment-attempt ID* (not amount) — Stripe will refuse to double-execute a request with a key it's already seen, even under concurrent redelivery.
- **DB-side**: a unique constraint on `(order_id)` or `(idempotency_key)` in your own charges table, so even if the Stripe call path is ever bypassed or misused, a second insert for the same order fails at the database, not silently succeeds.

That's belt-and-suspenders at rung 1 — the mistake becomes structurally impossible, not just less likely.

**Sweep for the class (this is the step that matters given "second time"):** the underlying hazard is "a queue consumer isn't idempotent under at-least-once redelivery" — that pattern is very unlikely to be unique to the payment worker. Worth checking every other queue consumer for the same shape: emails/notifications, webhook dispatch, ledger writes, inventory decrements, anything that mutates external or persistent state on message handling.

**Verify before closing it**: redeliver the same message twice in a test and confirm the second attempt is rejected (both at Stripe and at the DB constraint), not just "doesn't seem to double-charge in practice."

Want me to write this up as a `docs/poka-yoke/retro-2026-08-22-double-charge.md` per the skill's format, and/or do the sweep across your actual payment-worker repo (if you point me at it — this repo doesn't contain that code)?
```

</details>

---

## 25. `agent-guardrails|claude-haiku-4-5-20251001_with_skill|run-2|5`

**Assertion:** Recommends verifying the device actually fires rather than assuming it works

**Verdict:** 

<details><summary>response</summary>

```
The answer is in your own CLAUDE.md: **text is training, and training degrades.** Caps and repetition slow the degradation but don't stop it.

What you need isn't a better instruction—it's a *device*. The hooks need to live in `.git/hooks/` or a `.husky/` config so the harness (git itself) prevents the action, not Claude's memory.

**Two hook scripts:**

1. **.git/hooks/pre-commit** — blocks staged edits to `src/generated/`:
   ```bash
   #!/bin/sh
   if git diff --cached --name-only | grep -q '^src/generated/'; then
     echo "❌ Error: src/generated/ is read-only"
     exit 1
   fi
   ```

2. **.git/hooks/pre-push** — blocks force-push:
   ```bash
   #!/bin/sh
   if [[ "$*" == *"--force"* || "$*" == *"-f"* ]]; then
     echo "❌ Error: force push is blocked"
     exit 1
   fi
   ```

Make them executable: `chmod +x .git/hooks/pre-commit .git/hooks/pre-push`

**If you want this in version control** (so new clones get the hooks), use [husky](https://typicode.github.io/husky/) — it auto-installs hooks on `npm install`.

Once the device is in place, the 10% failure vanishes because git itself rejects the action. Claude can't bypass it—nobody can. That's why devices matter more than instructions.
```

</details>

---

## 26. `authz|agy-gemini-3.1-pro_with_skill|run-1|7`

**Assertion:** Recommends a cross-tenant test that attempts tenant A operations against tenant B resources

**Verdict:** 

<details><summary>response</summary>

```
I have reviewed [benchmarks/fixtures/documents.ts](file:///Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts) in accordance with the `authz` Poka-Yoke skill instructions. 

I've documented my findings and proposed fixes in the attached **Implementation Plan** artifact. I found several areas where one customer could see or mutate another customer's data, including an IDOR in the update path, client-controlled tenant IDs in the export path, and completely unscoped search/admin paths. 

Please review the plan, especially the **Open Questions** regarding whether you want these targeted fixes applied immediately or if you'd like to explore a broader Control-rung architectural change across the codebase. Click **Proceed** on the artifact when you're ready for me to apply the changes!
{"answer":"I have audited `benchmarks/fixtures/documents.ts` using the `authz` Poka-Yoke method. While the primary read path `getDocument` is properly scoped, there are **five critical paths** where one customer can see or modify another customer's data. \n\nHere are the ranked findings:\n\n### 1. Client-controlled Tenant ID in Export (IDOR)\n- **The Mistake:** `exportWorkspace` reads `tenantId` from `req.body` rather than from a trusted server-side session, and interpolates it directly into a raw SQL query.\n- **The Consequence:** Complete data exfiltration. Any authenticated user can pass another customer's `tenantId` and export their entire workspace (and execute arbitrary SQL).\n- **The Device:** Extract the `tenantId` from the trusted session (`req.session.tenantId`) and parameterize the query. *(Rung 1: Control)*\n\n### 2. Unscoped Update (IDOR)\n- **The Mistake:** `updateDocument` updates records by `id` without checking `session.tenantId`. \n- **The Consequence:** A user can overwrite another tenant's document if they know or guess the `documentId`. Write paths are often missed but are just as dangerous as reads.\n- **The Device:** Add `tenantId: session.tenantId` to the `where` clause. If Prisma requires a unique identifier, use `updateMany` with the tenant check. *(Rung 1: Control)*\n\n### 3. Unscoped Full-Text Search\n- **The Mistake:** `searchDocuments` takes a `session` argument but the raw SQL query only filters on the `search_vector`.\n- **The Consequence:** Search results will return matching documents across all tenants globally.\n- **The Device:** Add `AND tenant_id = ${session.tenantId}` to the `WHERE` clause in the raw query. *(Rung 1: Control)*\n\n### 4. Assumed Scope in Nested Resolvers\n- **The Mistake:** The `comments` and `attachments` GraphQL resolvers load data by `documentId` without checking the tenant. \n- **The Consequence:** If an attacker ever finds an unscoped path to a document, they can traverse into its comments and attachments. Nested resolvers are a common blind spot because they inherit nothing from the parent check.\n- **The Device:** Pass down `ctx.session.tenantId` into the `findMany` queries for nested relations. *(Rung 1/2: Defense in depth)*\n\n### 5. Unscoped Admin List\n- **The Mistake:** `adminListDocuments` returns all documents globally.\n- **The Consequence:** Unless this endpoint is strictly limited to super-admins of the entire platform, tenant admins will see all platform documents.\n- **The Device:** Scope the `findMany` call to `session.tenantId`. *(Rung 1: Control)*\n\n**Moving Forward:**\nFixing these individually brings us to Rung 2/3 (Warning/Detection). To reach Rung 1 (Control) systemically and make unscoped queries unrepresentable everywhere, we should consider implementing **Scoped Repositories** (passing `tenantId` into the constructor so the DB client cannot be reached without it) or **Database Row-Level Security (RLS)**.\n\nLet me know if you would like me to apply these targeted fixes to `documents.ts` to unblock your audit, or if you'd like to explore implementing Scoped Repositories!","toolAction":"Finishing task","toolSummary":"Finish task with findings"}
```

</details>

---

## 27. `retro|claude-sonnet-5_with_skill|run-4|5`

**Assertion:** Locates the hazard as a system property rather than as a worker bug or human error

**Verdict:** 

<details><summary>response</summary>

```
No — the check you added closes the exact bytes that broke last night, but it's a rung-3 (Detection) patch on a rung-0 hazard, and it's fragile enough on its own to cause a *new* kind of failure quietly.

**Separating the three things:**

- **Defect**: 340 customers double-charged in one worker run; refunded after the fact.
- **Mistake**: the queue redelivered the payment message (correct at-least-once behavior) and the retry called `charge()` again.
- **Hazard**: `charge()` has no idempotency guarantee — nothing in the code, the database, or Stripe's own API ties "one logical charge" to "at most one actual charge." That hazard is still there after your fix.

**Why the "recent charge, same amount" check isn't enough:**

1. **TOCTOU race.** If two redeliveries land close together (queues don't guarantee spacing), both can run the lookup before either has written the new charge. The check passes for both. This is the *same class* of bug that caused the incident — a read-then-act gap — just moved one level up.
2. **Wrong match key.** Amount + recency isn't a stable identity. Two different legitimate charges of the same amount to the same customer in a short window (two separate line items, a retry the customer intentionally initiated) will now silently get skipped — you've traded "customer charged twice" for "customer not charged and nobody notices," which is worse because it's invisible instead of loud.
3. **It's bolted onto one call site.** It doesn't stop the same shape of mistake anywhere else the same non-idempotent pattern exists.

**The Control-rung fix:** derive a stable idempotency key from the *business object being paid for* (order ID / invoice ID — not the queue message ID, not "amount + timestamp"), and:
- pass it as Stripe's native `idempotency_key` on `charges.create` — Stripe itself will return the original charge instead of creating a second one, atomically, on their side
- add a unique constraint on that key in your own ledger table, so the guarantee holds even if a code path ever bypasses Stripe's dedup

That's the "idempotency-key scope" decision that was still open from earlier — my recommendation: scope it to the durable business identifier (order/invoice ID), not the attempt or message ID. An attempt-scoped key just relocates the race to "did this attempt already run," which is the same TOCTOU problem in a new shape. An order-scoped key makes retries — whether from your queue or from Stripe's own webhook retries — collapse onto the same charge by construction, no lookup required.

**"Second time it's happened" — ask why nothing caught it.** Was there a test that simulates redelivery (call the handler twice with the same message) before this shipped? If not, that's the missing device: a regression test that proves `charge()` is a no-op on replay, run against the real handler, not a mock.

**Class sweep** — from the earlier pass on this: any other queue consumer with a side effect that isn't naturally idempotent has the same hazard — receipt emails, outbound webhooks, ledger/balance writes. Redelivery will hit those the same way it hit Stripe. Worth listing those consumers and confirming each either has its own idempotency key or is provably safe to run twice (e.g., a `SET` instead of an `INCREMENT`).

Want me to draft the idempotency-key + unique-constraint change against your actual worker code, and a redelivery regression test to go with it?
```

</details>

---

## 28. `retro|claude-sonnet-5_baseline|run-5|7`

**Assertion:** Treats 'second time this happened' as evidence for pushing to a Control-rung device

**Verdict:** 

<details><summary>response</summary>

```
No — the check you added narrows the failure window, it doesn't close it. Here's why, and what would.

**Defect**: 340 customers double-charged (refunded).
**Mistake**: the redelivered message called the charge path a second time.
**Hazard**: charging is not idempotent — nothing in your system guarantees two charge attempts for the same logical payment can't both succeed.

**Why the new check isn't the fix**: "look for a recent charge with the same amount before charging" is a check-then-act — the exact shape of bug you just had. Two things break it:

1. **TOCTOU race, same as before.** The scenario you described — worker times out waiting on Stripe, queue redelivers — often means the *first* charge already succeeded on Stripe's side, but your worker hadn't committed the charge record yet when the retry landed. The lookup finds nothing, charges again. Redelivery can also happen concurrently (two consumers), where both read "no recent charge" before either writes.
2. **"Same amount" is a weak key.** It produces false negatives (a customer legitimately charged the same amount twice in the window gets blocked) without giving you a real guarantee — it's not bound to a specific transaction.

This is a Detection-rung patch on a problem that needs a Control-rung fix.

**What would actually close it**:
- A stable idempotency key per logical charge — derived from the order/invoice ID, not freshly generated per attempt (a fresh UUID on retry defeats the whole point). Pass it as Stripe's `Idempotency-Key` header — Stripe then guarantees only one charge succeeds for that key even under concurrent retries, which is precisely your timeout→redelivery race.
- A unique constraint in your own DB on the order/invoice ID for the charges table, so even if application logic races, the second insert is rejected at the data layer, not inferred from a lookup.

Keep the "recent charge" check if you like, but as an alert/reconciliation signal, not the guard.

**The step worth not skipping**: you said this is the second time. That's a strong signal the hazard is bigger than the payment worker. Anything else consuming from that same queue and doing a non-idempotent side effect on redelivery — sending emails, firing webhooks, writing ledger entries — has the identical exposure. Worth a quick sweep of queue consumers before calling this closed.

Want me to write this up as `docs/poka-yoke/retro-2026-08-22-double-charge.md` per the retro skill format, and/or look at the actual worker code if it's in a repo I can see?
```

</details>

---

## 29. `authz|agy-gemini-3.1-pro_with_skill|run-1|4`

**Assertion:** Flags adminListDocuments as checking authentication but not authorization or tenant

**Verdict:** 

<details><summary>response</summary>

```
I have reviewed [benchmarks/fixtures/documents.ts](file:///Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts) in accordance with the `authz` Poka-Yoke skill instructions. 

I've documented my findings and proposed fixes in the attached **Implementation Plan** artifact. I found several areas where one customer could see or mutate another customer's data, including an IDOR in the update path, client-controlled tenant IDs in the export path, and completely unscoped search/admin paths. 

Please review the plan, especially the **Open Questions** regarding whether you want these targeted fixes applied immediately or if you'd like to explore a broader Control-rung architectural change across the codebase. Click **Proceed** on the artifact when you're ready for me to apply the changes!
{"answer":"I have audited `benchmarks/fixtures/documents.ts` using the `authz` Poka-Yoke method. While the primary read path `getDocument` is properly scoped, there are **five critical paths** where one customer can see or modify another customer's data. \n\nHere are the ranked findings:\n\n### 1. Client-controlled Tenant ID in Export (IDOR)\n- **The Mistake:** `exportWorkspace` reads `tenantId` from `req.body` rather than from a trusted server-side session, and interpolates it directly into a raw SQL query.\n- **The Consequence:** Complete data exfiltration. Any authenticated user can pass another customer's `tenantId` and export their entire workspace (and execute arbitrary SQL).\n- **The Device:** Extract the `tenantId` from the trusted session (`req.session.tenantId`) and parameterize the query. *(Rung 1: Control)*\n\n### 2. Unscoped Update (IDOR)\n- **The Mistake:** `updateDocument` updates records by `id` without checking `session.tenantId`. \n- **The Consequence:** A user can overwrite another tenant's document if they know or guess the `documentId`. Write paths are often missed but are just as dangerous as reads.\n- **The Device:** Add `tenantId: session.tenantId` to the `where` clause. If Prisma requires a unique identifier, use `updateMany` with the tenant check. *(Rung 1: Control)*\n\n### 3. Unscoped Full-Text Search\n- **The Mistake:** `searchDocuments` takes a `session` argument but the raw SQL query only filters on the `search_vector`.\n- **The Consequence:** Search results will return matching documents across all tenants globally.\n- **The Device:** Add `AND tenant_id = ${session.tenantId}` to the `WHERE` clause in the raw query. *(Rung 1: Control)*\n\n### 4. Assumed Scope in Nested Resolvers\n- **The Mistake:** The `comments` and `attachments` GraphQL resolvers load data by `documentId` without checking the tenant. \n- **The Consequence:** If an attacker ever finds an unscoped path to a document, they can traverse into its comments and attachments. Nested resolvers are a common blind spot because they inherit nothing from the parent check.\n- **The Device:** Pass down `ctx.session.tenantId` into the `findMany` queries for nested relations. *(Rung 1/2: Defense in depth)*\n\n### 5. Unscoped Admin List\n- **The Mistake:** `adminListDocuments` returns all documents globally.\n- **The Consequence:** Unless this endpoint is strictly limited to super-admins of the entire platform, tenant admins will see all platform documents.\n- **The Device:** Scope the `findMany` call to `session.tenantId`. *(Rung 1: Control)*\n\n**Moving Forward:**\nFixing these individually brings us to Rung 2/3 (Warning/Detection). To reach Rung 1 (Control) systemically and make unscoped queries unrepresentable everywhere, we should consider implementing **Scoped Repositories** (passing `tenantId` into the constructor so the DB client cannot be reached without it) or **Database Row-Level Security (RLS)**.\n\nLet me know if you would like me to apply these targeted fixes to `documents.ts` to unblock your audit, or if you'd like to explore implementing Scoped Repositories!","toolAction":"Finishing task","toolSummary":"Finish task with findings"}
```

</details>

---

## 30. `llm|claude-haiku-4-5-20251001_baseline|run-3|1`

**Assertion:** Recommends structured output against a schema rather than extracting values from prose

**Verdict:** 

<details><summary>response</summary>

```
**Subject: Refund bot extraction and deduplication** — applying the method directly.

The system prompt is rung 0 (training). It won't work because:
- **Extraction**: The LLM is doing its best to parse freeform chat, and "be careful" doesn't make extraction more accurate or bounded.
- **Deduplication**: A duplicate refund is a concurrency + retry problem that lives below the bot's layer. The LLM can't see what already happened in the database.

Here's what you actually need:

---

## Hazard 1: Wrong refund amount extracted

**The mistake:** LLM extracts `$50` when the customer said "refund $5000" or "$0.50", or hallucinates an amount that wasn't there.

**What happens:** Refund is too small (customer angry), too large (revenue loss), or nonsensical (customer confused about what happened).

**Is it silent?** Yes — the bot happily calls the API with a plausible-looking number.

---

**Device: Contact (rung 1) — lookup + validation**

Before calling the refund API, the bot must:
1. Extract the order ID from the chat (required, not optional)
2. Look up the order from your database
3. Validate the extracted amount against the order total: `extracted_amount <= order.total_amount`
4. Reject refunds that don't fit (throw, don't retry with prompting)

**Why this is rung 1:** The API will not execute a refund for an order ID with no matching order or for an amount larger than the order. The extraction error cannot become a refund — the type system (order exists + amount is in-bounds) makes it impossible.

**Alternative (rung 2 if lookup is hard):** The refund API validates and rejects, but you lose the ability to fast-fail in the bot.

---

## Hazard 2: Same order refunded twice

**The mistake:** Bot receives two support messages for the same order (customer follows up, message arrives twice, etc.), or bot retries the API call after a transient error, and both complete successfully.

**What happens:** Customer is refunded twice; you eat the revenue loss, or the second refund fails and customer loses trust.

**Is it silent?** Yes — nothing stops the second call from happening.

---

**Device: Motion-step + fixed-value (rung 1) — idempotency key**

The refund API must accept an `idempotency_key` parameter:
- The bot generates it as a deterministic hash: `idempotency_key = hash(order_id + reason + amount)`
- The API stores the key alongside each refund in the database
- On the second call with the same key, the API returns the *same* refund record without re-applying
- Database constraint: `UNIQUE(idempotency_key)` ensures only one refund per key ever reaches the ledger

**Why this is rung 1:** The second refund is physically impossible because the database constraint + idempotency check make it unrepresentable. The bot can retry as many times as it wants; only one refund ever executes.

**Why not just check the database first?** That's rung 2 (warning) — you check if the order was already refunded, and reject if so. But that has a TOCTOU race: between the check and the refund, another request can slip through. Idempotency keys are rung 1 because the database constraint prevents the race.

---

## Summary

| Problem | Today | Fix | Rung |
|---------|-------|-----|-----|
| Wrong amount | System prompt instruction | Order lookup + validation in bot, or validation in API | 1 |
| Duplicate refund | System prompt instruction | Idempotency keys + DB constraint in API | 1 |

Both belong in the **data layer and API contract**, not the LLM prompt. The bot's only job is to extract cleanly and pass an idempotency key. The API is responsible for catching bad amounts and preventing duplicates—because those are guarantees your customers need, regardless of who is calling the refund endpoint (support bot, admin dashboard, Stripe webhook, etc.).
```

</details>

---

## 31. `llm|claude-haiku-4-5-20251001_baseline|run-2|1`

**Assertion:** Recommends structured output against a schema rather than extracting values from prose

**Verdict:** 

<details><summary>response</summary>

```
System prompts can't enforce behavior—they're just suggestions. Your two issues need application-level devices, not training:

**For weird amounts:**
- Parse and validate on the backend before calling the refund API. Reject amounts outside expected ranges or in unexpected formats. Don't trust extraction.
- Log what the bot extracted vs. what the API received—if they diverge, you have a parsing problem.

**For duplicate refunds:**
- Use **idempotency keys** (order ID + timestamp or a request ID) in your refund API calls. Your backend should deduplicate: if the same idempotency key is seen twice, return the cached result instead of refunding again.
- Add a **unique constraint** in the database (`UNIQUE(order_id, refund_timestamp)` or similar) so duplicate writes fail at the database layer, not just at the application layer.
- This also protects against retries, network hangs, and the bot processing the same message twice.

**Add observability:**
- Log every refund with: extracted amount, validated amount, order ID, idempotency key, final result.
- Alert on: amount validation failures, duplicate idempotency key attempts, refunds outside thresholds.

**Consider a human gate:**
- For refunds over a threshold, route to a human approval step instead of auto-executing.

The pattern: validation on ingestion + idempotency + deduplication at storage. These are devices that *fail loudly* when something goes wrong, not instructions that degraded over time.
```

</details>

---

## 32. `ux|codex-gpt-5.6-terra_baseline|run-3|6`

**Assertion:** Notes that the server must enforce the deletion rules, not just the UI

**Verdict:** 

<details><summary>response</summary>

```
A modal helps, but it’s not sufficient—people click through confirmations.

Make deletion recoverable by default: move workspaces to a trash/soft-delete state with a clear restore option and a retention period. Then the modal can explain the consequence and offer “Move to trash”; reserve permanent deletion for a separate, deliberate action (for example, typing the workspace name).

That turns panic emails into self-service recovery.
```

</details>

---

## 33. `ux|codex-gpt-5.6-terra_baseline|run-2|5`

**Assertion:** If a dialog is retained, requires it to name the workspace and the scale of what is lost

**Verdict:** 

<details><summary>response</summary>

```
An “are you sure?” modal helps a little, but it’s training—not a safeguard. People will habituate and click through it.

Make deletion recoverable by default: move workspaces to a Trash/soft-delete state with a clear restore window and an immediate Undo action. Only permanently erase after that window, with an explicit irreversible confirmation if needed.
```

</details>

---

## 34. `audit|fable_with_skill|run-3|2`

**Assertion:** Flags the catch block that returns null as swallowing the error

**Verdict:** 

<details><summary>response</summary>

```
The write was denied too, so here's the audit in-conversation.

# Poka-Yoke Audit — `benchmarks/fixtures/payments.ts` — 2026-08-21

**Scope**: one file, 105 lines, six exported functions. Manual pass with the contact / fixed-value / motion-step lenses (the detector run wasn't permitted this session).
**Verdict**: `chargeCustomer` can charge a card twice and then report that it charged zero times. Fix that first, then the `transfer` swap-and-race, then the unbounded `DELETE`. Your nervousness is warranted — this passed review because every hazard *looks* like ordinary code.

## Findings (ranked by blast radius × ease)

### 1. Retry double-charges, then returns `null` — `payments.ts:44-60`
**Mistake**: Stripe times out *after* creating the charge; `retry=true` (or a caller retrying on `null`) calls again.
**Consequence**: two real charges, then `null` tells the caller *nothing* happened — inviting a third. No idempotency key anywhere. Fully silent.
**Today**: None → **Device**: required `IdempotencyKey` passed as Stripe's `{ idempotencyKey }` option; throw or return a discriminated result, never `null`. → **Control**

### 2. `transfer(from, to, amount)` swaps silently — `:17`
Both are `string`; `transfer(to, from, n)` compiles and moves money the wrong way. **Today**: None → branded `SourceAccountId`/`DestinationAccountId` → **Control** (object param `{from, to}` is the cheap Warning fallback).

### 3. `transfer` is a check-then-act race across two unrelated writes — `:21-32`
Two concurrent debits both pass the balance check and both write from the stale value; a crash between updates debits one side only. **Today**: None → one `$transaction` with `UPDATE … SET balance = balance - $n WHERE id = $from AND balance >= $n`, assert 1 row, plus `CHECK (balance >= 0)` in the schema. → **Control**

### 4. `to!` on a missing account: money leaves, never arrives — `:21,27,31`
If `to` doesn't exist, the debit succeeds and the credit throws. Partial, silent. → resolve both accounts before any write, ban `!` via `no-non-null-assertion`; fully closed by the transaction in #3. → **Control**

### 5. `purgeCanceledAccounts()` with no arg deletes every canceled account — `:80-91`
`olderThan` defaults to `new Date()` = "now", so the raw `DELETE` matches everything canceled, ever, uncapped, irreversible. Also `$executeRawUnsafe` with string interpolation. → make the cutoff required with a minimum age floor, cap rows / require `{confirmRows}`, use parameterized `deleteMany` and assert the returned count matches `doomed.length`. → **Control**

### 6. `handleWebhook` charges from an unverified, unparsed body — `:93-100`
No signature check, `JSON.parse` → `any`, so anyone who can POST can drive `chargeCustomer(anyCustomer, anyAmount)`. `event.data.amount` is probably `undefined` (Stripe's field is `amount_paid`), currency silently defaults to `usd`, and charging on `invoice.paid` is charging an invoice that's *already paid*. → `stripe.webhooks.constructEvent`, a zod schema, `event.id` as idempotency key. → **Control**

### 7. `updateSubscription` writes any string, then switches without `default` — `:67-78`
`"cancelled"` writes a nonsense status to the DB *before* the switch silently falls through; `canceled → active` is allowed. → literal-union status, a single `transition()` function doing write + side effect in one transaction, `assertNever` default. → **Control**

### 8. Three positional flags `currency, sendReceipt, retry` — `:40-42`
`chargeCustomer(id, 500, "eur", false)` reads as "no retry" but kills the receipt; `currency="usd"` default charges EUR accounts in USD. → `Money` carrying currency + options object with literal unions. → **Control**

### 9. Money as bare `number`, mixed units — `:12,17,63`
`transfer` takes `amount`, `chargeCustomer` takes `amountCents` — same module, two units. `applyDiscount` yields fractional cents. → integer `Money {cents, currency}` with explicit rounding. → **Control**

### 10. `void sendReceiptEmail(...)` — `:52`
Email failure vanishes. → outbox row in the same transaction (Control) or at minimum `await` + `no-floating-promises`. → **Warning** as written, since no outbox table exists yet.

## Set aside
Unused `WEBHOOK_TIMEOUT` string env read (F4); `Account.currency/status: string` (C4, covered by #8/#7); `JSON.parse` → `any` (folded into #6).

---

**Recap**: Ten findings, all rung None today; nine reach Control with branded IDs, a `Money` type, a required idempotency key, a single transaction in `transfer`, and a guarded purge. Per the audit skill I've proposed only — no edits. Two things I couldn't do: run `detect_hazards.py` and write `docs/poka-yoke/audit-2026-08-21.md` (both denied); say the word and I'll apply the devices with `poka-yoke:` marker comments, starting with #1–#3.

One note: the file header says this is a deliberately hazard-rich eval fixture — if "ship it" meant the benchmark rather than real billing code, then it's doing its job and should stay as-is.
```

</details>

---

## 35. `data|claude-sonnet-5_with_skill|run-1|7`

**Assertion:** Explains why a silently wrong number is more dangerous than a failed pipeline

**Verdict:** 

<details><summary>response</summary>

```
Using **poka-yoke:retro** + **poka-yoke:data** — this is an incident (retro decides what to fix) that broke in a pipeline (data decides which device).

**No.** A non-empty check doesn't touch the actual failure mode. During the whole three weeks, the table was never empty — the row count was fine. What broke was that a `NOT NULL` join value silently became a valid-looking `0`. Your test asserts volume; the incident was in reconciliation. It would have passed every single day of the outage. That's the "check that cannot fail" pattern this repo's own CLAUDE.md calls out — before trusting it, you'd want to prove it actually goes red against this incident, and it doesn't.

**The three things, separated:**
- **Defect**: dashboard understated revenue for 3 weeks, caught only at finance close.
- **Mistake**: upstream renamed a column; the join started missing; nothing surfaced that.
- **Hazard**: `COALESCE(revenue, 0)` makes "no match" and "zero revenue" indistinguishable. That's the real target — the coalesce, not the missing test.

**Devices, ranked by rung (data's four questions: is it there / right amount / shaped right / does it agree):**

1. **Control** — stop coalescing the join result. Either let the null propagate and fail the build on any NULL in a required revenue column post-join, or replace the silent `COALESCE(revenue, 0)` with something that can't produce a plausible wrong value — a sentinel that fails downstream, or a `NOT NULL` constraint on the joined column before it's allowed to be zero.
2. **Warning/gate** — assert join match-rate (e.g. `null_rate` on `revenue` pre-coalesce) is ~0, and block promotion to the published table if it isn't. This is the one that would have fired on day one of the rename.
3. **Detection, but the right kind** — a **reconciliation** check: warehouse revenue total vs. the source system's total, within tolerance, daily. Row count wouldn't have moved during this incident; the total would have.
4. **Boundary** — a data contract on the upstream table so a column rename breaks loudly (or quarantines) instead of silently producing nulls that get zeroed.

Your row-count test is still worth keeping — it's real Detection-rung coverage for a different failure mode (partial load, filter that matches nothing) — just don't let it stand in for the check that would have actually caught *this* incident.

Two decisions I need from you before I write these: what reconciliation tolerance is acceptable (exact match vs. some %), and what should happen when the null-rate gate trips — block the pipeline, or quarantine the unmatched rows and publish the rest?
```

</details>

---

## 36. `ops|claude-haiku-4-5-20251001_baseline|run-1|5`

**Assertion:** Recommends a CI gate that blocks destructive DDL from landing alongside application code

**Verdict:** 

<details><summary>response</summary>

```
I see a couple of things worth checking before Friday afternoon, given the context:

**Database migration safety**: Dropping a column is a data operation that's trickier than code changes. Even with CI green, I'd verify:
- **Backward compatibility during rollout** — if old code briefly runs alongside new, does it handle the missing column gracefully? (Or are you doing a coordinated deploy?)
- **Rollback plan** — if production fails, can you restore the column quickly, or restore from backup?

**Timing context**: The startup hook mentions a recent double-charge incident and ongoing SOC2 audit. Friday afternoon deploys can be risky if something goes sideways and your team isn't fully present for troubleshooting. Is this:
- Low-risk data cleanup (column never actually used in weeks)?
- Critical for compliance or an incident follow-up (worth the risk)?

**Questions for you**:
1. What's your on-call coverage tonight/weekend if something breaks?
2. Is the column definitely dead (grep confirms nothing reads it after your changes)?
3. Did you test the deploy path itself (staging deploy, or dry-run)?

If it's truly a small, low-risk cleanup and you have confidence in rollback, green CI/tests, and coverage tonight — you know your system better than I do. But "small change" + "Friday afternoon" + recent production incidents is a flag I'd raise. What's the downside of merging now and deploying Monday morning?
```

</details>

---

## 37. `agent-guardrails|opus_with_skill|run-2|2`

**Assertion:** Recommends permission deny rules in settings.json with concrete syntax

**Verdict:** 

<details><summary>response</summary>

```
I read the router and it points this at `agent-guardrails` — "CLAUDE.md says X but it still does Y" is its exact trigger. Here's what it says, applied to your two rules.

## The diagnosis, in one sentence

Nothing is wrong with your prose — **instructions to an agent are rung zero.** Caps and repetition don't change that; they're training, and training degrades under long contexts, compaction, and subagents that never read your CLAUDE.md. One-in-ten *is* what a well-written instruction looks like. The fix is a device, not better wording.

Your two rules need different devices, and it's worth knowing why.

## Rule 1 — `src/generated/` — a deny rule is enough

Pure path match, no logic. In `.claude/settings.json`:

```jsonc
{
  "permissions": {
    "deny": [
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)"
    ]
  }
}
```

Gap to know about: this covers the Edit/Write tools, not a Bash-mediated write (`sed -i src/generated/...`). Close that with a header in each generated file plus a CI check that regeneration produces no diff — Detection, but the file is reversible so it doesn't need Control.

## Rule 2 — force push — needs a hook

Deny entries match the **start** of the command. `Bash(git push --force:*)` catches `git push --force origin main` and misses `git push origin main --force`, which is the form that will bite you. Add the prefix denies anyway, then wire the shipped guard for real coverage:

```jsonc
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash|Edit|Write|Read",
      "hooks": [{
        "type": "command",
        "command": "python3 \"${CLAUDE_PROJECT_DIR}\"/.claude/hooks/guard_dangerous_commands.py"
      }]
    }]
  }
}
```

Copy `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py` into `.claude/hooks/`. Its regex is `\bgit\s+push\b.*(--force(?!-with-lease)|...-f...)` — flag anywhere, and `--force-with-lease` stays allowed.

## The part people drop: the message

The agent reads the denial and acts on it, so a bare refusal produces a creative workaround. The shipped reason says *"Force-push can destroy commits that exist only on the remote. Use `--force-with-lease` if you must rewrite, and ask the user before rewriting shared history."* Write yours for `src/generated/` the same way — name the codegen command it should run instead.

## Where it lives

`.claude/settings.json`, **committed**. In `settings.local.json` it protects one machine, which is the same failure mode as documenting it.

## Verify — I could not run this here

This session has no exec permission, so I did not test the guard; do this before trusting it:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main --force"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect: deny + --force-with-lease
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect: silence
```

An unverified hook is worse than none — a regex that doesn't match the real command string does nothing while looking like protection.

`★ Insight ─────────────────────────────────────`
The interesting split here isn't force-push vs. generated files, it's **irreversible vs. reversible**. Force-push destroys remote-only commits — Control, no exceptions. A stray edit to `src/generated/` is one `git checkout` away from fixed, so it earns a deny rule and a CI check but not a hook.
`─────────────────────────────────────────────────`

Want me to write both files into this repo (or point me at the target repo)? One decision shapes the deny message: **what's the legitimate regeneration command for `src/generated/`?** The message should name it, so the agent runs that instead of hand-editing — that redirect is what turns a blocked call into the right one.
```

</details>

---

## 38. `ops|claude-haiku-4-5-20251001_baseline|run-3|5`

**Assertion:** Recommends a CI gate that blocks destructive DDL from landing alongside application code

**Verdict:** 

<details><summary>response</summary>

```
Small change + green CI is good, but Friday afternoon deployments hinge on a few things I'd verify first:

1. **Data migration safety** — When you dropped `legacy_email`, did you run a backfill/verification query to confirm no production rows still need it? A column drop is instant but irreversible, so "we updated the three places" is only half the story if something else queries it at runtime.

2. **Rollback window** — If something breaks post-deploy, how long until someone can roll back? Friday afternoon into evening means a narrow window before oncall context switches.

3. **Downstream services** — Does anything outside this service (webhooks, other services reading this table, old API clients) still reference `legacy_email`? The three code paths you updated might not be exhaustive.

4. **Deployment procedure** — Is this a standard blue-green / canary, or a direct deploy? Column drops can be invisible until a query hits it under load.

**Quick take:** If (1) you've verified no stray queries reference it, (2) rollback is <5 minutes, and (3) you've checked downstream, it's low-risk enough for Friday afternoon. Otherwise, queue it for Monday morning and let the weekend be quiet.

What does your deployment process look like, and have you verified the data side?
```

</details>

---

## 39. `retro|fable_with_skill|run-3|5`

**Assertion:** Locates the hazard as a system property rather than as a worker bug or human error

**Verdict:** 

<details><summary>response</summary>

```
Short answer: **no.** The fix you shipped is a check-then-act race — it is the same hazard wearing a different coat, and it also covers only one of the sites where this mistake is available. Here's the retro, in the skill's shape.

## Defect / mistake / hazard

- **Defect**: 340 customers charged twice.
- **Mistake**: the redelivered message ran `charge()` a second time.
- **Hazard**: **a charge can be created without an idempotency key, and nothing at the Stripe or database layer refuses the second one.** The queue redelivering is not the bug — at-least-once delivery is the normal case. The system *permitted* a retry to become a second charge.

"Second time this has happened" is the tell: the first fix addressed the mistake, not the hazard.

## Why the new check is not enough (catalog hazard M5 + M2)

"Look for a recent charge with the same amount, then charge" is a `SELECT` followed by a side effect:

1. **It races.** Two workers pull the redelivered message and the original concurrently (exactly what happens after a timeout). Both see no recent charge; both charge. The window is the full Stripe round-trip — the one that just timed out.
2. **Timeout doesn't mean failure.** The first attempt timed out *client-side*; Stripe may have completed it. A "recent charge" lookup against your own DB won't see a charge you never got the response for. That is precisely the 340-customer case.
3. **Same amount ≠ same intent.** Two legitimate $20 orders inside the window get silently dropped — you've traded a loud duplicate for a silent lost sale. And it's a time-windowed heuristic that you'll tune, and re-tune.
4. **Single site.** It lives in this worker. Anything else that can reach `charge()` — an admin retry button, a backfill script, a cron, the other service — still has the mistake available.

Rung: this is **Detection at best**, bypassable by concurrency.

## Devices, by rung

| Device | Rung | Covers |
|---|---|---|
| `charge()` takes a **required** idempotency key (not optional) derived from the *order/intent ID*, not the message ID, and passes it to Stripe as `Idempotency-Key`. Stripe then returns the original result for a retry — including one whose first response you never received. | **Control** | every caller, including the timed-out one |
| A `payment_attempts` table with `UNIQUE (order_id)` (or `(account_id, idempotency_key)`), where the row is **inserted in the same transaction as the intent to charge**, before calling Stripe. A redelivery hits the constraint, reads the stored status, and reconciles instead of charging. | **Control** | every code path, every language, `psql` included |
| Bind the key to the payload (amount, currency, customer) — same key, different payload → error, not a silent no-op. | Warning | misuse of the key itself |
| Reconciliation job: Stripe charges per customer per order vs. your ledger; alert on >1. | Detection | anything the above misses; proves the device works |
| Regression test: deliver the same message twice, concurrently, assert one Stripe call. | Detection | this path |

Only the first two change the shape of the mistake. Required key is cheap; the DB constraint is what makes it durable against the next caller someone writes.

## What should have caught it, and didn't

Something to ask explicitly in your retro: why did the first incident's fix not produce the constraint? Usually the answer is "the key was added as optional to avoid touching callers" — which is the hazard reappearing as a convenience.

## Class sweep (do this before closing)

Grep for every external mutation reachable from a queue consumer, cron, or retry: emails, webhooks, refunds (your refund script from last night — was *it* idempotent?), inventory decrements, ledger writes. Count them and report the number; it changes what the fix is worth. If you point me at the repo I'll run `plugins/poka-yoke/scripts/detect_hazards.py --id M2` across it and list the sites.

## Verify before you call it closed

Replay the same message twice concurrently against staging and watch the second attempt get refused by the constraint — and a different-payload reuse get rejected. A device that has never fired is a belief.

**Recap**: the amount-lookup check is a race and a heuristic; it does not prevent recurrence. Install a required idempotency key on `charge()` (passed through to Stripe) plus a unique-constrained attempt row reserved before the call, sweep every other retryable side effect for the same shape, and prove the device fires. Next step on your side: share the worker/`charge()` code or repo path and I'll do the sweep and draft the constraint.
```

</details>

---

## 40. `build-form|agy-gemini-3.1-pro_with_skill|run-1|1`

**Assertion:** Produces actual working component code rather than only a list of recommendations

**Verdict:** 

<details><summary>response</summary>

```
Here is the bulk actions component, implementing the mistake-proofing devices for interfaces. I’ve included the state handling, the explicit scope escalation for "Select All", and the mutation shapes.

```tsx
import React, { useState } from 'react';

export type Document = {
  id: string;
  title: string;
  updatedAt: string;
  ownerName: string;
};

// Simulated API calls with required idempotency keys (M2 device)
async function archiveDocuments(args: {
  documentIds: string[];
  selectAllMatching: boolean;
  idempotencyKey: string;
}) {
  // POST /api/documents/bulk-archive
}

async function deleteDocuments(args: {
  documentIds: string[];
  selectAllMatching: boolean;
  idempotencyKey: string;
}) {
  // POST /api/documents/bulk-delete
}

interface DocumentBulkActionsProps {
  selectedIds: Set<string>;
  totalMatchingCount: number;
  pageCount: number;
  onClearSelection: () => void;
  onSelectAllMatching: () => void;
  selectAllMatching: boolean;
}

export function DocumentBulkActions({
  selectedIds,
  totalMatchingCount,
  pageCount,
  onClearSelection,
  onSelectAllMatching,
  selectAllMatching,
}: DocumentBulkActionsProps) {
  const [isArchiving, setIsArchiving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');

  // Fixed-value inspection: calculate the exact scale of the action
  const selectedCount = selectAllMatching ? totalMatchingCount : selectedIds.size;
  
  // Distinguish "page selected" from "all matching selected" to prevent scope escalation
  const isAllOnPageSelected = selectedIds.size === pageCount && pageCount > 0;
  const showSelectAllPrompt = isAllOnPageSelected && !selectAllMatching && totalMatchingCount > pageCount;

  if (selectedIds.size === 0 && !selectAllMatching) {
    return null;
  }

  const handleArchive = async () => {
    setIsArchiving(true);
    try {
      await archiveDocuments({
        documentIds: Array.from(selectedIds),
        selectAllMatching,
        idempotencyKey: crypto.randomUUID(), // Structural double-submit prevention
      });
      // In a real implementation: trigger a "Documents archived. [Undo]" toast here
      onClearSelection();
    } catch (error) {
      console.error('Archive failed:', error);
    } finally {
      setIsArchiving(false);
    }
  };

  // Fixed-value constraint: user must reproduce the exact object count to proceed
  const expectedConfirmText = `Delete ${selectedCount} documents`;

  const handleDelete = async () => {
    if (deleteConfirmText !== expectedConfirmText) return;

    setIsDeleting(true);
    try {
      await deleteDocuments({
        documentIds: Array.from(selectedIds),
        selectAllMatching,
        idempotencyKey: crypto.randomUUID(), // Structural double-submit prevention
      });
      onClearSelection();
      setShowDeleteConfirm(false);
      setDeleteConfirmText('');
    } catch (error) {
      console.error('Delete failed:', error);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <>
      <div 
        className="fixed bottom-6 left-1/2 transform -translate-x-1/2 bg-white shadow-2xl rounded-lg border border-gray-200 px-6 py-4 flex items-center space-x-8 z-40"
        role="region"
        aria-label="Bulk actions"
      >
        <div className="flex flex-col min-w-[200px]">
          <span className="font-semibold text-gray-900">
            {selectedCount} document{selectedCount === 1 ? '' : 's'} selected
          </span>
          
          {showSelectAllPrompt && (
            <button
              onClick={onSelectAllMatching}
              className="text-sm text-blue-600 hover:text-blue-800 hover:underline text-left mt-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
            >
              Select all {totalMatchingCount} matching documents
            </button>
          )}
          
          {selectAllMatching && (
            <button
              onClick={onClearSelection}
              className="text-sm text-blue-600 hover:text-blue-800 hover:underline text-left mt-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
            >
              Clear selection
            </button>
          )}
        </div>

        <div className="flex items-center space-x-3 border-l border-gray-200 pl-8">
          <button
            onClick={handleArchive}
            disabled={isArchiving || isDeleting}
            aria-disabled={isArchiving || isDeleting}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isArchiving ? 'Archiving...' : 'Archive'}
          </button>

          <button
            onClick={() => setShowDeleteConfirm(true)}
            disabled={isArchiving || isDeleting}
            aria-disabled={isArchiving || isDeleting}
            className="px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Delete
          </button>
        </div>
      </div>

      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center p-4 z-50">
          <div 
            className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 space-y-5"
            role="dialog"
            aria-labelledby="delete-dialog-title"
          >
            <div>
              <h2 id="delete-dialog-title" className="text-xl font-semibold text-gray-900">
                Delete {selectedCount} documents permanently?
              </h2>
              <p className="mt-2 text-sm text-gray-600">
                This action cannot be undone. To confirm, type <strong>{expectedConfirmText}</strong> below.
              </p>
            </div>
            
            <div>
              <label htmlFor="confirm-delete" className="sr-only">
                Confirm deletion text
              </label>
              <input
                id="confirm-delete"
                type="text"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                className="block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-red-500 sm:text-sm"
                placeholder={expectedConfirmText}
                autoComplete="off"
                disabled={isDeleting}
              />
            </div>
            
            <div className="flex justify-end space-x-3 pt-2">
              <button
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setDeleteConfirmText('');
                }}
                disabled={isDeleting}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleteConfirmText !== expectedConfirmText || isDeleting}
                aria-disabled={deleteConfirmText !== expectedConfirmText || isDeleting}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isDeleting ? 'Deleting...' : 'Delete forever'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
```

### Device notes

- **Scope escalation and double submission are impossible.** The UI structurally distinguishes between "Select page" and "Select all" so a user cannot accidentally wipe the dataset while trying to clear their screen (**Warning**). The component generates a `crypto.randomUUID()` idempotency key on submission, guaranteeing that a UI double-click or network retry will not re-execute the bulk action (**Control**).
- **Accidental deletion requires work.** The confirmation dialog abandons the useless "Are you sure?" in favor of fixed-value inspection, requiring the user to type the exact number of documents being destroyed to proceed (**Warning**). 
- **Archive is left frictionless on purpose.** Archiving is recoverable effort. Putting a confirmation dialog in front of it trains users to blind-click through gates. We leave it as an immediate action, assuming the application will display a grace-period "Undo" toast once the call returns.
{"answer":"Here is the bulk actions component, implementing the mistake-proofing devices for interfaces. I’ve included the state handling, the explicit scope escalation for \"Select All\", and the mutation shapes.\n\n```tsx\nimport React, { useState } from 'react';\n\nexport type Document = {\n  id: string;\n  title: string;\n  updatedAt: string;\n  ownerName: string;\n};\n\n// Simulated API calls with required idempotency keys (M2 device)\nasync function archiveDocuments(args: {\n  documentIds: string[];\n  selectAllMatching: boolean;\n  idempotencyKey: string;\n}) {\n  // POST /api/documents/bulk-archive\n}\n\nasync function deleteDocuments(args: {\n  documentIds: string[];\n  selectAllMatching: boolean;\n  idempotencyKey: string;\n}) {\n  // POST /api/documents/bulk-delete\n}\n\ninterface DocumentBulkActionsProps {\n  selectedIds: Set\u003cstring\u003e;\n  totalMatchingCount: number;\n  pageCount: number;\n  onClearSelection: () =\u003e void;\n  onSelectAllMatching: () =\u003e void;\n  selectAllMatching: boolean;\n}\n\nexport function DocumentBulkActions({\n  selectedIds,\n  totalMatchingCount,\n  pageCount,\n  onClearSelection,\n  onSelectAllMatching,\n  selectAllMatching,\n}: DocumentBulkActionsProps) {\n  const [isArchiving, setIsArchiving] = useState(false);\n  const [isDeleting, setIsDeleting] = useState(false);\n  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);\n  const [deleteConfirmText, setDeleteConfirmText] = useState('');\n\n  // Fixed-value inspection: calculate the exact scale of the action\n  const selectedCount = selectAllMatching ? totalMatchingCount : selectedIds.size;\n  \n  // Distinguish \"page selected\" from \"all matching selected\" to prevent scope escalation\n  const isAllOnPageSelected = selectedIds.size === pageCount \u0026\u0026 pageCount \u003e 0;\n  const showSelectAllPrompt = isAllOnPageSelected \u0026\u0026 !selectAllMatching \u0026\u0026 totalMatchingCount \u003e pageCount;\n\n  if (selectedIds.size === 0 \u0026\u0026 !selectAllMatching) {\n    return null;\n  }\n\n  const handleArchive = async () =\u003e {\n    setIsArchiving(true);\n    try {\n      await archiveDocuments({\n        documentIds: Array.from(selectedIds),\n        selectAllMatching,\n        idempotencyKey: crypto.randomUUID(), // Structural double-submit prevention\n      });\n      // In a real implementation: trigger a \"Documents archived. [Undo]\" toast here\n      onClearSelection();\n    } catch (error) {\n      console.error('Archive failed:', error);\n    } finally {\n      setIsArchiving(false);\n    }\n  };\n\n  // Fixed-value constraint: user must reproduce the exact object count to proceed\n  const expectedConfirmText = `Delete ${selectedCount} documents`;\n\n  const handleDelete = async () =\u003e {\n    if (deleteConfirmText !== expectedConfirmText) return;\n\n    setIsDeleting(true);\n    try {\n      await deleteDocuments({\n        documentIds: Array.from(selectedIds),\n        selectAllMatching,\n        idempotencyKey: crypto.randomUUID(), // Structural double-submit prevention\n      });\n      onClearSelection();\n      setShowDeleteConfirm(false);\n      setDeleteConfirmText('');\n    } catch (error) {\n      console.error('Delete failed:', error);\n    } finally {\n      setIsDeleting(false);\n    }\n  };\n\n  return (\n    \u003c\u003e\n      \u003cdiv \n        className=\"fixed bottom-6 left-1/2 transform -translate-x-1/2 bg-white shadow-2xl rounded-lg border border-gray-200 px-6 py-4 flex items-center space-x-8 z-40\"\n        role=\"region\"\n        aria-label=\"Bulk actions\"\n      \u003e\n        \u003cdiv className=\"flex flex-col min-w-[200px]\"\u003e\n          \u003cspan className=\"font-semibold text-gray-900\"\u003e\n            {selectedCount} document{selectedCount === 1 ? '' : 's'} selected\n          \u003c/span\u003e\n          \n          {showSelectAllPrompt \u0026\u0026 (\n            \u003cbutton\n              onClick={onSelectAllMatching}\n              className=\"text-sm text-blue-600 hover:text-blue-800 hover:underline text-left mt-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded\"\n            \u003e\n              Select all {totalMatchingCount} matching documents\n            \u003c/button\u003e\n          )}\n          \n          {selectAllMatching \u0026\u0026 (\n            \u003cbutton\n              onClick={onClearSelection}\n              className=\"text-sm text-blue-600 hover:text-blue-800 hover:underline text-left mt-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded\"\n            \u003e\n              Clear selection\n            \u003c/button\u003e\n          )}\n        \u003c/div\u003e\n\n        \u003cdiv className=\"flex items-center space-x-3 border-l border-gray-200 pl-8\"\u003e\n          \u003cbutton\n            onClick={handleArchive}\n            disabled={isArchiving || isDeleting}\n            aria-disabled={isArchiving || isDeleting}\n            className=\"px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors\"\n          \u003e\n            {isArchiving ? 'Archiving...' : 'Archive'}\n          \u003c/button\u003e\n\n          \u003cbutton\n            onClick={() =\u003e setShowDeleteConfirm(true)}\n            disabled={isArchiving || isDeleting}\n            aria-disabled={isArchiving || isDeleting}\n            className=\"px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors\"\n          \u003e\n            Delete\n          \u003c/button\u003e\n        \u003c/div\u003e\n      \u003c/div\u003e\n\n      {showDeleteConfirm \u0026\u0026 (\n        \u003cdiv className=\"fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center p-4 z-50\"\u003e\n          \u003cdiv \n            className=\"bg-white rounded-xl shadow-2xl max-w-md w-full p-6 space-y-5\"\n            role=\"dialog\"\n            aria-labelledby=\"delete-dialog-title\"\n          \u003e\n            \u003cdiv\u003e\n              \u003ch2 id=\"delete-dialog-title\" className=\"text-xl font-semibold text-gray-900\"\u003e\n                Delete {selectedCount} documents permanently?\n              \u003c/h2\u003e\n              \u003cp className=\"mt-2 text-sm text-gray-600\"\u003e\n                This action cannot be undone. To confirm, type \u003cstrong\u003e{expectedConfirmText}\u003c/strong\u003e below.\n              \u003c/p\u003e\n            \u003c/div\u003e\n            \n            \u003cdiv\u003e\n              \u003clabel htmlFor=\"confirm-delete\" className=\"sr-only\"\u003e\n                Confirm deletion text\n              \u003c/label\u003e\n              \u003cinput\n                id=\"confirm-delete\"\n                type=\"text\"\n                value={deleteConfirmText}\n                onChange={(e) =\u003e setDeleteConfirmText(e.target.value)}\n                className=\"block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-red-500 sm:text-sm\"\n                placeholder={expectedConfirmText}\n                autoComplete=\"off\"\n                disabled={isDeleting}\n              /\u003e\n            \u003c/div\u003e\n            \n            \u003cdiv className=\"flex justify-end space-x-3 pt-2\"\u003e\n              \u003cbutton\n                onClick={() =\u003e {\n                  setShowDeleteConfirm(false);\n                  setDeleteConfirmText('');\n                }}\n                disabled={isDeleting}\n                className=\"px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 transition-colors\"\n              \u003e\n                Cancel\n              \u003c/button\u003e\n              \u003cbutton\n                onClick={handleDelete}\n                disabled={deleteConfirmText !== expectedConfirmText || isDeleting}\n                aria-disabled={deleteConfirmText !== expectedConfirmText || isDeleting}\n                className=\"px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors\"\n              \u003e\n                {isDeleting ? 'Deleting...' : 'Delete forever'}\n              \u003c/button\u003e\n            \u003c/div\u003e\n          \u003c/div\u003e\n        \u003c/div\u003e\n      )}\n    \u003c/\u003e\n  );\n}\n```\n\n### Device notes\n\n- **Scope escalation and double submission are impossible.** The UI structurally distinguishes between \"Select page\" and \"Select all\" so a user cannot accidentally wipe the dataset while trying to clear their screen (**Warning**). The component generates a `crypto.randomUUID()` idempotency key on submission, guaranteeing that a UI double-click or network retry will not re-execute the bulk action (**Control**).\n- **Accidental deletion requires work.** The confirmation dialog abandons the useless \"Are you sure?\" in favor of fixed-value inspection, requiring the user to type the exact number of documents being destroyed to proceed (**Warning**). \n- **Archive is left frictionless on purpose.** Archiving is recoverable effort. Putting a confirmation dialog in front of it trains users to blind-click through gates. We leave it as an immediate action, assuming the application will display a grace-period \"Undo\" toast once the call returns.","toolAction":"Finishing the task","toolSummary":"Finish the task"}
```

</details>

---

## 41. `design|claude-sonnet-5_baseline|run-1|4`

**Assertion:** Provides a single transition function or otherwise constrains how state changes

**Verdict:** 

<details><summary>response</summary>

```
Quick misuse pass before the shape, per poka-yoke:

- **Optional-bag trap**: a flat `{status, trialEndsAt?, retryCount?, gracePeriodEndsAt?, cancelReason?, voluntary?, renewsAt?}` type permits `status: "active"` with a `cancelReason` sitting there, or `"canceled"` with a live `renewsAt`. 6 fields, most of them meaningless in most states.
- **New status added later**: someone adds `"paused"` next year — does every switch statement that handles subscriptions get a compile error, or does it silently fall into whatever the `default` branch does?
- **Swappable IDs**: `subscriptionId` and `customerId` are both strings — nothing stops `charge(customerId, subscriptionId)` from compiling backwards.
- **Cancellation is really two shapes wearing one skin**: "involuntary" (card declined, fraud) and "voluntary" (user clicked cancel) usually have different valid reasons and different downstream handling (dunning vs. exit survey). A flat `reason: string` doesn't stop someone writing `voluntary: true, reason: "payment_failed"`.

Here's the shape that makes those unsayable:

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type SubscriptionId = Brand<string, "SubscriptionId">;
export type CustomerId = Brand<string, "CustomerId">;

// Two nested unions, not two booleans-plus-strings — a payment-failure
// reason can't be paired with voluntary:true, and vice versa.
export type Cancellation =
  | { voluntary: true; reason: VoluntaryCancelReason }
  | { voluntary: false; reason: InvoluntaryCancelReason };

export type VoluntaryCancelReason =
  | "too_expensive"
  | "missing_features"
  | "switched_competitor"
  | "no_longer_needed"
  | "other";

export type InvoluntaryCancelReason =
  | "payment_failed"
  | "fraud_flagged"
  | "chargeback";

export type Subscription =
  | {
      status: "trialing";
      id: SubscriptionId;
      customerId: CustomerId;
      trialEndsAt: Date;
    }
  | {
      status: "active";
      id: SubscriptionId;
      customerId: CustomerId;
      renewsAt: Date;
    }
  | {
      status: "past_due";
      id: SubscriptionId;
      customerId: CustomerId;
      retryCount: number;
      gracePeriodEndsAt: Date;
    }
  | {
      status: "canceled";
      id: SubscriptionId;
      customerId: CustomerId;
      cancellation: Cancellation;
    };
```

Exhaustiveness so the compiler — not a person — catches a missed status:

```ts
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

function nextMilestone(sub: Subscription): Date | null {
  switch (sub.status) {
    case "trialing":  return sub.trialEndsAt;
    case "active":    return sub.renewsAt;
    case "past_due":  return sub.gracePeriodEndsAt;
    case "canceled":  return null;
    default:          return assertNever(sub);
  }
}
```

`nextMilestone` couldn't compile if it forgot a case, and it can't reach into `retryCount` from the `"active"` branch — TypeScript narrows the union per-branch.

At the API/DB boundary, parse rather than trust — a `zod` discriminated union rejects a malformed row instead of letting `any` carry it inward:

```ts
import { z } from "zod";

const SubscriptionSchema = z.discriminatedUnion("status", [
  z.object({ status: z.literal("trialing"), id: z.string(), customerId: z.string(), trialEndsAt: z.coerce.date() }),
  z.object({ status: z.literal("active"), id: z.string(), customerId: z.string(), renewsAt: z.coerce.date() }),
  z.object({ status: z.literal("past_due"), id: z.string(), customerId: z.string(), retryCount: z.number().int().nonnegative(), gracePeriodEndsAt: z.coerce.date() }),
  z.object({ status: z.literal("canceled"), id: z.string(), customerId: z.string(), cancellation: CancellationSchema }),
]);
```

`★ Insight ─────────────────────────────────────`
1. **Discriminated unions vs. optional bags** — TypeScript narrows on the literal `status` field, so inside `case "past_due"` the compiler *knows* `retryCount` and `gracePeriodEndsAt` exist and `renewsAt` doesn't. An optional-bag type gives you none of that — you'd be doing manual `if (sub.retryCount !== undefined)` checks everywhere, and nothing stops a caller from constructing the nonsense combination in the first place.
2. **Branding costs nothing at runtime** — `Brand<string, "X">` is a phantom type that only exists for `tsc`; it compiles to a plain string. You get compile-time protection against ID mix-ups for free, but only if `strict: true` + `tsc --noEmit` actually run in CI — a branded type in an unchecked repo is just a comment.
3. **Nesting `Cancellation` instead of two flat fields** is the same move one level down: it turns "voluntary + payment_failed" from a bug waiting to happen into a type error.
`─────────────────────────────────────────────────`

One thing left open on purpose: **legal state transitions aren't encoded here** (can you go `past_due` → `trialing`? probably not, but that's a business rule, not a shape rule). That's usually a `transition(sub, event)` function with a `never`-exhaustive switch over valid `(from, event)` pairs — worth doing once retry/dunning logic exists, not before.

The reason lists (`VoluntaryCancelReason` / `InvoluntaryCancelReason`) are placeholders — I don't know what your actual dunning/exit-survey flow tracks. That's a real decision: too few reasons and your churn analytics are useless, too many and support agents pick randomly. Could you fill in the real list (5-10 lines) for both unions based on what your cancellation flow / Stripe webhook already reports?
```

</details>

---

## 42. `retro|agy-gemini-3.1-pro_baseline|run-2|5`

**Assertion:** Locates the hazard as a system property rather than as a worker bug or human error

**Verdict:** 

<details><summary>response</summary>

```
To answer your question directly: **No, that check is not enough.** 

In fact, the "check for a recent charge" approach falls straight into two traps described in this repository's hazard catalog:

1. **Check-then-act race (M5):** If the queue redelivers the message and two workers process it concurrently, both will run the check at the same time, find no recent charge, and both will hit Stripe. It passes the unit tests but fails under concurrency in production.
2. **False Positives:** If a customer legitimately buys two identical items for the same amount in quick succession, your worker will incorrectly block the second purchase.

The permanent, mistake-proof fix for this is **M2 (Non-idempotent retryable effects)**: requiring an **Idempotency Key**. Stripe natively supports this. If you pass a unique idempotency key (generated when the checkout session starts) to Stripe, it guarantees that retrying the exact same request will simply return the original successful response instead of charging the card again. 

I've created a detailed implementation plan artifact for you to review that outlines how we can permanently fix this using idempotency keys and database constraints. Please review the plan, specifically the **Open Questions** regarding your database and where the unique key is generated, and let me know if you approve so we can proceed!
{"answer":"I have created a detailed implementation plan in the `idempotency_plan.md` artifact that explains why checking for recent charge amounts is insufficient due to **check-then-act race conditions (M5)** and false positives. \n\nThe plan outlines the recommended approach to solve this permanently using **Idempotency Keys (M2)** to guarantee exactly-once processing with Stripe. Please review the open questions in the plan regarding where the unique key is generated and your database setup. Let me know if you approve or if you have any feedback!","toolAction":"Finishing task","toolSummary":"Finish task"}
```

</details>

---

## 43. `ux|claude-sonnet-5_baseline|run-4|4`

**Assertion:** Recommends type-the-workspace-name confirmation for the irreversible case

**Verdict:** 

<details><summary>response</summary>

```
That's actually already been evaluated earlier in this session — a confirm modal was rejected in favor of soft-delete: 30-day trash + an undo toast. The reasoning: confirmation modals for actions people take repeatedly (even rarely) get reflexively clicked through — "modal blindness" — so they don't actually catch the mistake, they just add friction. A soft-delete gives you a real recovery path *after* the mistake happens, which is what actually stops the support emails.

The recommendation was blocked on three decisions: what happens to billing/seats during the grace period, whether a deleted workspace's slug can be reused before the 30 days are up, and who's allowed to restore (owner only, or any admin).

Want to go with soft-delete+trash instead, or do you still want the modal (e.g., as a stopgap before trash is built)?
```

</details>

---

## 44. `guardrails|fable_baseline|run-2|5`

**Assertion:** Notes that branch protection is what makes a CI check actually required

**Verdict:** 

<details><summary>response</summary>

```
Stop trying to get people to follow it. Two weeks of half-compliance after a retro agreement, a CONTRIBUTING.md entry, a Slack pin, and two standup mentions isn't a people problem — it's the expected decay curve of an instruction. Every channel you've used so far relies on someone remembering at the moment they type `git commit`. The fix is to make the unformatted/untyped PR *unable to exist*, so nobody has to remember anything.

In order of leverage:

**1. Make CI the gate, not the reminder (do this first, today).**
Add a CI job that runs `<formatter> --check` and the type checker, then mark it a *required status check* in branch protection. Now an unformatted PR physically cannot merge. Nobody has to notice, nag, or review for it. This is the only step that actually closes the gap; everything below just makes it less annoying.

**2. Make compliance the path of least resistance.**
A required check that fails is friction; friction breeds resentment and "skip CI" hacks. So pair it with:
- A pre-commit hook (via `pre-commit`, `husky`, `lefthook`, whatever fits your stack) that *runs the formatter*, not just checks it. The commit comes out formatted without the author doing anything.
- Make the hook install itself — wire `pre-commit install` into `make setup` / `npm postinstall` / the dev-container, so a fresh clone has it without anyone reading a doc.
- Commit editor config (`.vscode/settings.json`, `.editorconfig`) enabling format-on-save. Most people will never hit the hook because the editor already did it.

**3. Typing needs a ratchet, not a rule.**
"Add annotations to new code" is unenforceable as stated — no tool knows what's "new." Pick a mechanical definition: run the type checker in strict mode with a baseline file of existing errors (mypy `--baseline`-style tooling, pyright's `baseline`, or a counted-errors script) and fail CI if the count *rises*. That converts a judgment call into a number that can only go down.

**4. Then delete the instruction.**
Once the device exists, shrink the CONTRIBUTING.md paragraph to "formatting and types are enforced in CI; run `make setup` to get the hooks." Prose that duplicates a check is just another thing to drift.

**Verify the device before trusting it.** Push a deliberately unformatted branch and watch the check go red. A check that's never failed is a rumour — and formatter checks in particular are notorious for silently passing because they were pointed at the wrong directory.

One honest caveat: the first week after you flip the required check on, a handful of in-flight PRs will go red and people will grumble. Auto-fixing (step 2) and a one-time "format the whole repo" commit (add its SHA to `.git-blame-ignore-revs`) take most of that sting out.

If you want, point me at the repo and stack and I'll wire up the CI check, the self-installing hook, and the type-error ratchet.
```

</details>

---

## 45. `ux|fable_baseline|run-2|1`

**Assertion:** Explains habituation or click-through blindness as why frequent dialogs stop working

**Verdict:** 

<details><summary>response</summary>

```
Honestly, no — not as the fix. An "Are you sure?" modal is the weakest device on the ladder for this problem, and it'll likely fail you in the exact way you're trying to avoid.

**Why it won't work**

The users emailing support in a panic aren't people who lacked resolve — they clicked delete *on purpose*, on the wrong thing, or without understanding the blast radius. "Are you sure?" asks about resolve; it doesn't tell them anything they didn't already believe. And once people see the modal a few times, they click through it reflexively. You'll add friction to every legitimate delete and still get the panic emails.

**What actually fixes it, strongest first**

1. **Make it reversible — soft-delete with a retention window.** Mark the workspace deleted, hide it, hard-purge after 7–30 days. Support's reply becomes "click Restore" instead of "sorry, it's gone." This is a backend change, not a UI change, which is why it gets skipped — but it's the only option that turns the incident into a non-event.
2. **Grace-period undo.** Delete immediately, show "Workspace deleted. Undo" for ~10s. Zero friction on the happy path, full recovery on the mistaken one. Needs #1 underneath it anyway.
3. **Type-to-confirm** (GitHub-style: type the workspace name). Only if deletion is *genuinely* irreversible and high-blast-radius. Can't be done reflexively, but it's theater if used for everything.
4. **A modal that states facts, not resolve.** If you do keep a modal, make it "Delete *Acme Prod* — 14 members, 2,300 documents, permanently?" That's a real check. "Are you sure?" is not.

**My recommendation:** do #1 and #2 together, and drop the modal entirely. If the data model makes soft-delete hard right now, do #4 as a stopgap — name the workspace, show the counts, make Delete the non-default button and visually separate it from Cancel — and put soft-delete on the roadmap as the real fix.

If you want, point me at the delete handler and the workspace model and I'll implement soft-delete + undo in your stack.
```

</details>

---

## 46. `guardrails|codex-gpt-5.6-terra_with_skill|run-1|2`

**Assertion:** Notes that pre-commit is bypassable with --no-verify and must be backed by a CI check

**Verdict:** 

<details><summary>response</summary>

```
Stop adding reminders; make the PR path reject violations.

- Run the formatter automatically in a pre-commit hook for fast feedback.
- Add a required CI check that runs the formatter in check-only mode. Protect the main branch so a failing check cannot merge.
- Require type checking in that same protected CI path. For existing untyped code, baseline current errors and ratchet: reject new type errors and require new modules to meet the stricter setting.
- Have CI comment or fail with the exact fix command, e.g. “Run `… format`” or “Add annotations / resolve these type errors.”
- Prove each gate: deliberately submit unformatted and untyped code, confirm CI blocks it, then fix it and confirm it passes.

The hook is a **warning** device—useful because it catches mistakes in seconds, but bypassable. Required CI plus branch protection is the actual **control**: unformatted or newly untyped changes cannot become merged defects. Your CONTRIBUTING entry, Slack pin, and standup reminders were all training; they cannot reliably enforce the rule.
```

</details>

---

## 47. `retro|agy-gemini-3.1-pro_baseline|run-1|8`

**Assertion:** Attributes cause to the system, not to any person

**Verdict:** 

<details><summary>response</summary>

```
## Fixing Payment Double Charges using Idempotency

The heuristic check you added (looking for a recent charge of the same amount) is **not enough** and is fundamentally unsafe for a few reasons:

1. **Race Conditions:** If the queue redelivers the message rapidly, two worker instances could run simultaneously. Both would check the database for a recent charge, both would see nothing, and both would issue a charge to Stripe.
2. **False Positives:** If a customer legitimately makes two identical purchases in a short timeframe (e.g. buying a ticket, then immediately deciding to buy a second one for a friend), your check will block the second valid charge.
3. **Eventual Consistency:** If you are reading from a replica, the first charge might not be visible yet when the second attempt checks the database.

The industry-standard solution for this exact problem is to use **Idempotency Keys**. 

### How Stripe Idempotency Keys Work
When you include an `Idempotency-Key` header in your request, Stripe caches the result. If a request with the exact same key is sent again within 24 hours, Stripe returns the original cached response instead of processing a new charge. This perfectly solves the "timeout and retry" problem because the retry will simply fetch the result of the first attempt.

---

## User Review Required

> [!IMPORTANT]
> The idempotency key must be tied to the **unique event or order**, not randomly generated at the time the charge request is made. If you generate a random UUID right before calling Stripe, retries will get a different UUID and you will double-charge again. Do you currently have a unique identifier on your queue messages (e.g., `event_id`, `order_id`, or `invoice_id`) that we can use?

> [!WARNING]
> If your worker updates local database state after the Stripe charge (e.g., updating an order status), you also need to make the worker idempotent locally. If the worker crashes *after* Stripe succeeds but *before* the DB update, the next retry will get the cached Stripe success, but we must ensure we don't accidentally send the user two receipts or fulfill the order twice.

---

## Open Questions

> [!NOTE]
> 1. What does the queue message payload look like? Is there a unique `message_id` or `transaction_id` we can extract?
> 2. Are you using the official Stripe Node.js SDK? The plan assumes you are, as it natively supports idempotency keys.

---

## Proposed Changes

### Payment Module
Implementing the idempotency key in the Stripe charge function.

#### [MODIFY] payments.ts
We need to update the `chargeCustomer` signature (and any callers) to accept an idempotency key and pass it in the Stripe request options.

```typescript
// benchmarks/fixtures/payments.ts (or your actual worker file)

export async function chargeCustomer(
  customerId: string,
  amountCents: number,
  idempotencyKey: string, // [NEW] Require an idempotency key
  currency = "usd",
  sendReceipt = true,
  retry = false,
) {
  try {
    const charge = await stripe.charges.create(
      {
        customer: customerId,
        amount: amountCents,
        currency,
      },
      {
        idempotencyKey, // [NEW] Pass to Stripe
      }
    );

    if (sendReceipt) {
      void sendReceiptEmail(customerId, charge.id);
    }
    return charge;
  } catch (e) {
    // If we retry, we must reuse the exact same idempotencyKey!
    if (retry) {
      return chargeCustomer(customerId, amountCents, idempotencyKey, currency, sendReceipt, false);
    }
    return null;
  }
}
```

#### [MODIFY] worker handler
Where you consume the queue message, you must pass the message's unique identifier as the idempotency key.

```typescript
// Example Worker Update

export async function handleWebhook(body: string) {
  const event = JSON.parse(body);
  
  if (event.type === "invoice.paid") {
    // Use the unique event ID (or invoice ID) as the idempotency key
    await chargeCustomer(
      event.data.customer, 
      event.data.amount,
      event.id // MUST be a unique, consistent ID for this exact transaction
    );
  }
}
```

---

## Verification Plan

### Automated Tests
1. **Mock Stripe to timeout:** We will write a test that mocks the Stripe API to timeout on the first call and succeed on the second call.
2. **Assert on idempotency key:** We will verify that both the initial call and the retry call passed the exact same `Idempotency-Key` to the mocked Stripe client.
3. **Assert single execution:** We will verify that local side-effects (like DB updates or email receipts) are only triggered once.

### Manual Verification
1. Enqueue a payment task in a staging environment.
2. Intercept the network request to Stripe and drop it (or force the worker to crash after calling Stripe).
3. Let the queue redeliver the message.
4. Verify in the Stripe Dashboard (Staging) that only a single charge was created, and that the second request shows in the logs as an "Idempotent Replayed" response.
```

</details>

---

## 48. `build-endpoint|agy-gemini-3.1-pro_with_skill|run-1|6`

**Assertion:** Scopes the write so one tenant or user cannot refund another's order

**Verdict:** 

<details><summary>response</summary>

```
I have applied the `design` and `authz` mistake-proofing methods to this endpoint. I assumed the existing `Order` table has a `stripeChargeId` column to link to Stripe, and that we are using a PostgreSQL database.

Here is the complete inline implementation:

### 1. Handler

```typescript
import { z } from "zod";
import { PrismaClient, RefundStatus } from "@prisma/client";
import Stripe from "stripe";

// --- Branded Types ---
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type OrderId = Brand<string, "OrderId">;
export type TenantId = Brand<string, "TenantId">;
export type UserId = Brand<string, "UserId">;
export type IdempotencyKey = Brand<string, "IdempotencyKey">;
export type Cents = Brand<number, "Cents">;

// --- Boundary Parsing ---
const RefundRequestSchema = z.object({
  orderId: z.string().uuid().brand<"OrderId">(),
  amountCents: z.number().int().positive().brand<"Cents">(),
  reason: z.string().min(1),
  // Require idempotency key from the client
  idempotencyKey: z.string().min(1).brand<"IdempotencyKey">(),
});

interface Session {
  userId: UserId;
  tenantId: TenantId;
}

export async function handleRefund(
  req: { body: unknown },
  session: Session,
  db: PrismaClient,
  stripe: Stripe
) {
  // 1. Boundary: Parse, don't validate (C7)
  const parsed = RefundRequestSchema.safeParse(req.body);
  if (!parsed.success) {
    throw new Error("Invalid request"); // In real app: return 400 with parsed.error
  }
  const { orderId, amountCents, reason, idempotencyKey } = parsed.data;

  // 2. Tenant Isolation (Authz)
  const order = await db.order.findUnique({
    where: { 
      id: orderId,
      tenantId: session.tenantId 
    },
    select: { id: true, stripeChargeId: true, totalCents: true }
  });

  if (!order) {
    // Return generic error to avoid leaking cross-tenant existence
    throw new Error("Order not found");
  }

  if (amountCents > order.totalCents) {
    throw new Error("Refund amount exceeds order total");
  }

  // 3. Two-phase commit / Idempotency via DB (F5, M2)
  let refund;
  try {
    refund = await db.refund.create({
      data: {
        orderId,
        amountCents,
        reason,
        idempotencyKey,
        status: RefundStatus.PENDING,
      }
    });
  } catch (error: any) {
    // Prisma unique constraint violation (P2002) means this was already attempted
    if (error.code === "P2002") {
      return db.refund.findUniqueOrThrow({ where: { idempotencyKey } });
    }
    throw error;
  }

  // 4. External mutation with idempotency
  try {
    const stripeRefund = await stripe.refunds.create(
      {
        charge: order.stripeChargeId,
        amount: amountCents,
        reason: "requested_by_customer",
        metadata: { internalReason: reason, orderId }
      },
      { idempotencyKey } // Pass the DB-backed guarantee to Stripe
    );

    // 5. Finalize state
    return await db.refund.update({
      where: { id: refund.id },
      data: {
        status: RefundStatus.SUCCEEDED,
        stripeRefundId: stripeRefund.id,
      }
    });
  } catch (error) {
    await db.refund.update({
      where: { id: refund.id },
      data: { status: RefundStatus.FAILED }
    });
    throw error;
  }
}
```

### 2. Prisma Schema Additions

```prisma
// Assuming this is added to your schema.prisma
enum RefundStatus {
  PENDING
  SUCCEEDED
  FAILED
}

model Order {
  id             String   @id @default(uuid())
  tenantId       String
  totalCents     Int
  currency       String
  stripeChargeId String   // Assumed existing
  refunds        Refund[]
}

model Refund {
  id             String       @id @default(uuid())
  orderId        String
  amountCents    Int
  reason         String
  createdAt      DateTime     @default(now())

  // Poka-yoke additions
  idempotencyKey String       @unique
  status         RefundStatus @default(PENDING)
  stripeRefundId String?

  order          Order        @relation(fields: [orderId], references: [id])
}
```

### 3. SQL Migration

```sql
CREATE TYPE "RefundStatus" AS ENUM ('PENDING', 'SUCCEEDED', 'FAILED');

ALTER TABLE "Refund" ADD COLUMN "idempotencyKey" TEXT NOT NULL;
ALTER TABLE "Refund" ADD COLUMN "status" "RefundStatus" NOT NULL DEFAULT 'PENDING';
ALTER TABLE "Refund" ADD COLUMN "stripeRefundId" TEXT;

-- Prevent double-refunds at the DB level
CREATE UNIQUE INDEX "Refund_idempotencyKey_key" ON "Refund"("idempotencyKey");

-- Prevent negative refunds at the DB level
ALTER TABLE "Refund" ADD CONSTRAINT "refund_amount_positive" CHECK ("amountCents" > 0);
```

---

### Mistake-Proofing Reasoning

I enumerated the following misuse hazards and designed them out:

1. **Cross-tenant data leak (Authz)**: A caller passes an `orderId` belonging to another tenant.
   - **Device**: Scoped repository query `where: { id: orderId, tenantId: session.tenantId }`. Reaches **Control**. The application cannot fetch an order outside the current tenant's scope, and returns a generic 404-equivalent to avoid leaking existence.
2. **Double refunds from retries (M2)**: A user double-clicks the refund button, or the queue retries the job. 
   - **Device**: Required `idempotencyKey` backed by a `UNIQUE` database constraint, mapped directly to Stripe's idempotency key. Reaches **Control**. A second attempt returns the first attempt's result rather than charging the business twice.
3. **Partial writes / dropped network (F5)**: The server crashes after hitting Stripe but before inserting the `Refund` row, silently losing the record of the money moving.
   - **Device**: Strict ordering. We insert the `Refund` row with `status = PENDING` *before* calling Stripe. Reaches **Control**. If the server crashes, the client can safely retry with the same key, and we will resume tracking.
4. **Parameter swapping & Primitive obsession (C1 / C3)**: Passing `tenantId` where `orderId` is expected, or passing a float for `amountCents`.
   - **Device**: Zod parsing at the boundary and Branded Types (`OrderId`, `TenantId`, `Cents`). Reaches **Control**. The handler strictly refuses to compile if IDs are swapped, and rejects non-integer/negative amounts before any business logic runs.

**What I explicitly left possible:**
- If Stripe *succeeds* but the network connection drops before Stripe's response reaches the server, the database row will remain stuck in `PENDING` (or transition to `FAILED` if a generic timeout is caught). This is left possible because strict two-phase commit is impossible across a network boundary. It requires a successive check (Detection rung) — a background reconciliation job that queries Stripe for any `PENDING` refunds older than 5 minutes.
{"answer":"I have applied the `design` and `authz` mistake-proofing methods to this endpoint. I assumed the existing `Order` table has a `stripeChargeId` column to link to Stripe, and that we are using a PostgreSQL database.\n\nHere is the complete inline implementation:\n\n### 1. Handler\n\n```typescript\nimport { z } from \"zod\";\nimport { PrismaClient, RefundStatus } from \"@prisma/client\";\nimport Stripe from \"stripe\";\n\n// --- Branded Types ---\ndeclare const brand: unique symbol;\ntype Brand\u003cT, B\u003e = T \u0026 { readonly [brand]: B };\n\nexport type OrderId = Brand\u003cstring, \"OrderId\"\u003e;\nexport type TenantId = Brand\u003cstring, \"TenantId\"\u003e;\nexport type UserId = Brand\u003cstring, \"UserId\"\u003e;\nexport type IdempotencyKey = Brand\u003cstring, \"IdempotencyKey\"\u003e;\nexport type Cents = Brand\u003cnumber, \"Cents\"\u003e;\n\n// --- Boundary Parsing ---\nconst RefundRequestSchema = z.object({\n  orderId: z.string().uuid().brand\u003c\"OrderId\"\u003e(),\n  amountCents: z.number().int().positive().brand\u003c\"Cents\"\u003e(),\n  reason: z.string().min(1),\n  // Require idempotency key from the client\n  idempotencyKey: z.string().min(1).brand\u003c\"IdempotencyKey\"\u003e(),\n});\n\ninterface Session {\n  userId: UserId;\n  tenantId: TenantId;\n}\n\nexport async function handleRefund(\n  req: { body: unknown },\n  session: Session,\n  db: PrismaClient,\n  stripe: Stripe\n) {\n  // 1. Boundary: Parse, don't validate (C7)\n  const parsed = RefundRequestSchema.safeParse(req.body);\n  if (!parsed.success) {\n    throw new Error(\"Invalid request\"); // In real app: return 400 with parsed.error\n  }\n  const { orderId, amountCents, reason, idempotencyKey } = parsed.data;\n\n  // 2. Tenant Isolation (Authz)\n  const order = await db.order.findUnique({\n    where: { \n      id: orderId,\n      tenantId: session.tenantId \n    },\n    select: { id: true, stripeChargeId: true, totalCents: true }\n  });\n\n  if (!order) {\n    // Return generic error to avoid leaking cross-tenant existence\n    throw new Error(\"Order not found\");\n  }\n\n  if (amountCents \u003e order.totalCents) {\n    throw new Error(\"Refund amount exceeds order total\");\n  }\n\n  // 3. Two-phase commit / Idempotency via DB (F5, M2)\n  let refund;\n  try {\n    refund = await db.refund.create({\n      data: {\n        orderId,\n        amountCents,\n        reason,\n        idempotencyKey,\n        status: RefundStatus.PENDING,\n      }\n    });\n  } catch (error: any) {\n    // Prisma unique constraint violation (P2002) means this was already attempted\n    if (error.code === \"P2002\") {\n      return db.refund.findUniqueOrThrow({ where: { idempotencyKey } });\n    }\n    throw error;\n  }\n\n  // 4. External mutation with idempotency\n  try {\n    const stripeRefund = await stripe.refunds.create(\n      {\n        charge: order.stripeChargeId,\n        amount: amountCents,\n        reason: \"requested_by_customer\",\n        metadata: { internalReason: reason, orderId }\n      },\n      { idempotencyKey } // Pass the DB-backed guarantee to Stripe\n    );\n\n    // 5. Finalize state\n    return await db.refund.update({\n      where: { id: refund.id },\n      data: {\n        status: RefundStatus.SUCCEEDED,\n        stripeRefundId: stripeRefund.id,\n      }\n    });\n  } catch (error) {\n    await db.refund.update({\n      where: { id: refund.id },\n      data: { status: RefundStatus.FAILED }\n    });\n    throw error;\n  }\n}\n```\n\n### 2. Prisma Schema Additions\n\n```prisma\n// Assuming this is added to your schema.prisma\nenum RefundStatus {\n  PENDING\n  SUCCEEDED\n  FAILED\n}\n\nmodel Order {\n  id             String   @id @default(uuid())\n  tenantId       String\n  totalCents     Int\n  currency       String\n  stripeChargeId String   // Assumed existing\n  refunds        Refund[]\n}\n\nmodel Refund {\n  id             String       @id @default(uuid())\n  orderId        String\n  amountCents    Int\n  reason         String\n  createdAt      DateTime     @default(now())\n\n  // Poka-yoke additions\n  idempotencyKey String       @unique\n  status         RefundStatus @default(PENDING)\n  stripeRefundId String?\n\n  order          Order        @relation(fields: [orderId], references: [id])\n}\n```\n\n### 3. SQL Migration\n\n```sql\nCREATE TYPE \"RefundStatus\" AS ENUM ('PENDING', 'SUCCEEDED', 'FAILED');\n\nALTER TABLE \"Refund\" ADD COLUMN \"idempotencyKey\" TEXT NOT NULL;\nALTER TABLE \"Refund\" ADD COLUMN \"status\" \"RefundStatus\" NOT NULL DEFAULT 'PENDING';\nALTER TABLE \"Refund\" ADD COLUMN \"stripeRefundId\" TEXT;\n\n-- Prevent double-refunds at the DB level\nCREATE UNIQUE INDEX \"Refund_idempotencyKey_key\" ON \"Refund\"(\"idempotencyKey\");\n\n-- Prevent negative refunds at the DB level\nALTER TABLE \"Refund\" ADD CONSTRAINT \"refund_amount_positive\" CHECK (\"amountCents\" \u003e 0);\n```\n\n---\n\n### Mistake-Proofing Reasoning\n\nI enumerated the following misuse hazards and designed them out:\n\n1. **Cross-tenant data leak (Authz)**: A caller passes an `orderId` belonging to another tenant.\n   - **Device**: Scoped repository query `where: { id: orderId, tenantId: session.tenantId }`. Reaches **Control**. The application cannot fetch an order outside the current tenant's scope, and returns a generic 404-equivalent to avoid leaking existence.\n2. **Double refunds from retries (M2)**: A user double-clicks the refund button, or the queue retries the job. \n   - **Device**: Required `idempotencyKey` backed by a `UNIQUE` database constraint, mapped directly to Stripe's idempotency key. Reaches **Control**. A second attempt returns the first attempt's result rather than charging the business twice.\n3. **Partial writes / dropped network (F5)**: The server crashes after hitting Stripe but before inserting the `Refund` row, silently losing the record of the money moving.\n   - **Device**: Strict ordering. We insert the `Refund` row with `status = PENDING` *before* calling Stripe. Reaches **Control**. If the server crashes, the client can safely retry with the same key, and we will resume tracking.\n4. **Parameter swapping \u0026 Primitive obsession (C1 / C3)**: Passing `tenantId` where `orderId` is expected, or passing a float for `amountCents`.\n   - **Device**: Zod parsing at the boundary and Branded Types (`OrderId`, `TenantId`, `Cents`). Reaches **Control**. The handler strictly refuses to compile if IDs are swapped, and rejects non-integer/negative amounts before any business logic runs.\n\n**What I explicitly left possible:**\n- If Stripe *succeeds* but the network connection drops before Stripe's response reaches the server, the database row will remain stuck in `PENDING` (or transition to `FAILED` if a generic timeout is caught). This is left possible because strict two-phase commit is impossible across a network boundary. It requires a successive check (Detection rung) — a background reconciliation job that queries Stripe for any `PENDING` refunds older than 5 minutes.","toolAction":"Finished with task","toolSummary":"Finish task"}
```

</details>

---

## 49. `agent-guardrails|opus_baseline|run-3|0`

**Assertion:** States that instructions to a model are not enforcement, regardless of wording or emphasis

**Verdict:** 

<details><summary>response</summary>

```
Nothing about the wording. Caps and repetition are the only levers prose has, and you've pulled both — that's why the failure rate is 1-in-10 rather than 1-in-3. **An instruction in CLAUDE.md is training, and training degrades**: under compaction, in long contexts, and in subagents that never loaded the file. You can't get a rule that's read-and-remembered to 100%. You can get a rule that's *enforced* to 100%.

Your two rules need different devices, and only one of them is a one-liner.

## 1. Generated files — a deny rule is enough

`.claude/settings.json`, committed (not `settings.local.json` — that protects your laptop only, which is the same failure as documenting it):

```jsonc
{
  "permissions": {
    "deny": [
      // poka-yoke: src/generated/ is build output; edits vanish on regen [control]
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)",
      "Bash(git push --force:*)",
      "Bash(git push -f:*)"
    ]
  }
}
```

## 2. Force-push — the deny rule above is a trap on its own

Those two Bash patterns are prefix matches. They catch `git push --force origin main`. They do **not** catch `git push origin main --force`, `git push -f`, or `git push --force-with-lease`'s ugly cousins. A rule that looks enforced and isn't is worse than no rule, because you stop watching for it.

Conditional matching needs a `PreToolUse` hook that inspects the command. This repo already ships one — `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py:31` handles exactly this case, with `--force-with-lease` deliberately left allowed.

## 3. The deny message is the actual device

A bare refusal makes the agent invent a workaround, usually worse. The message is read and acted on, so it has to name what was blocked, why, and the alternative:

> Blocked: edit to `src/generated/user_api.ts`. This directory is build output — your change disappears on the next codegen run. Edit the source schema in `schema/` and run `make codegen`.

That's the one place prose belongs in a guardrail.

## 4. Prove it fires — both directions

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main --force"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect deny + message
echo '{"tool_name":"Bash","tool_input":{"command":"git push --force-with-lease"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect empty (still allowed)
```

Then in a live session, actually ask Claude to force-push and watch it get refused. Untested hooks fail open more often than people expect.

`★ Insight ─────────────────────────────────────`
- Hooks fire on subagent tool calls too. That's likely where a chunk of your 1-in-10 lives — a subagent never read CLAUDE.md.
- Both rules are still *local* devices. The receive-side pair is `git push --force` branch protection on the remote, and a CI job that reruns codegen and fails on a non-empty diff. Those hold even when someone runs Claude with hooks off.
`─────────────────────────────────────────────────`

---

One decision I'd want yours on before writing this: **how does legitimate regeneration get through?** Options are (a) codegen runs via `make codegen`, so `Bash` isn't blocked and only direct `Edit`/`Write` are — simplest, and what the config above does; or (b) an explicit escape hatch the agent can invoke with a stated reason. (b) is more flexible and one rationalization away from useless.

Tell me which, plus the repo path, and I'll write the settings + hook and run the failure test in front of you.
```

</details>

---

## 50. `design|claude-sonnet-5_baseline|run-3|5`

**Assertion:** Explicitly names which misuses the design makes impossible

**Verdict:** 

<details><summary>response</summary>

```
**Misuse enumeration first** — a `Subscription` interface with all fields optional (`trialEndsAt?`, `retryCount?`, `cancelReason?`, `renewalDate?`) would let you construct `{status: "active", cancelReason: "..."}`  and every reader would have to remember which fields are valid for which status. That's the hazard to close.

```typescript
// --- Branded IDs: a SubscriptionId and CustomerId are both strings underneath,
// but they mean different things and should never be swappable at a call site.
type Brand<T, B extends string> = T & { readonly __brand: B };
type SubscriptionId = Brand<string, "SubscriptionId">;
type CustomerId = Brand<string, "CustomerId">;

// --- Cancellation reasons: "voluntary: boolean" + "reason: string" is itself a
// mini bag-of-optionals — it lets `{ voluntary: true, reason: "payment_failed" }`
// type-check even though that reason only makes sense when voluntary is false.
// Nesting the union closes that gap instead of just commenting "don't do that."
type VoluntaryReason = "too_expensive" | "missing_features" | "switched_competitor" | "no_longer_needed" | "other";
type InvoluntaryReason = "payment_failed" | "fraud_flagged" | "chargeback" | "compliance_hold";

type Cancellation =
  | { voluntary: true; reason: VoluntaryReason; feedback?: string }
  | { voluntary: false; reason: InvoluntaryReason };

interface SubscriptionBase {
  id: SubscriptionId;
  customerId: CustomerId;
}

interface TrialingSubscription extends SubscriptionBase {
  status: "trialing";
  trialEndsAt: Date;
}

interface ActiveSubscription extends SubscriptionBase {
  status: "active";
  renewalDate: Date;
}

interface PastDueSubscription extends SubscriptionBase {
  status: "past_due";
  retryCount: number;        // invariant: >= 0 — enforce in the constructor below
  gracePeriodEndsAt: Date;
}

interface CanceledSubscription extends SubscriptionBase {
  status: "canceled";
  canceledAt: Date;
  cancellation: Cancellation;
}

type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;
```

Two devices worth calling out on top of the union itself:

```typescript
// Exhaustiveness: adding a fifth status ("paused"?) next year breaks every
// switch that doesn't handle it, at compile time, not in prod three weeks later.
function assertNever(x: never): never {
  throw new Error(`Unhandled subscription status: ${JSON.stringify(x)}`);
}

function hasAccess(sub: Subscription): boolean {
  switch (sub.status) {
    case "trialing":  return sub.trialEndsAt > new Date();
    case "active":    return true;
    case "past_due":  return sub.gracePeriodEndsAt > new Date();
    case "canceled":  return false;
    default:          return assertNever(sub);
  }
}

// Illegal transitions: cancelSubscription only accepts the three non-canceled
// variants, so "cancel an already-canceled subscription" is a type error, not
// a runtime check you have to remember to write.
type CancelableSubscription = TrialingSubscription | ActiveSubscription | PastDueSubscription;

function cancelSubscription(
  sub: CancelableSubscription,
  cancellation: Cancellation,
  canceledAt: Date,
): CanceledSubscription {
  return { id: sub.id, customerId: sub.customerId, status: "canceled", canceledAt, cancellation };
}
```

`★ Insight ─────────────────────────────────────`
1. This is the "bag of optionals vs. sum type" hazard from the design ritual — an interface with N optional fields legally admits 2^N states, most of which are garbage. The discriminated union on `status` admits exactly 4.
2. `cancelSubscription`'s parameter type is doing typestate work without a full typestate machine: excluding `CanceledSubscription` from the input type is cheaper than a runtime `if (sub.status === "canceled") throw`, and it can't be forgotten.
3. TypeScript's structural typing is the honest limit here — nothing stops someone from hand-building a `PastDueSubscription` object literal with `retryCount: -1`, bypassing any constructor you write. Closing that fully needs private constructors/nominal branding, which is usually not worth the ceremony unless this type crosses a lot of hands.
`─────────────────────────────────────────────────`

One thing I deliberately left open, and it's the one only you can close: **which transitions are legal**. Can `past_due` go back to `active` directly, or must it pass through a payment-confirmation step? Can `trialing` skip straight to `canceled` with a refund? That's your billing policy, not a type-design question — I'd rather you encode it than guess. Want to sketch the transition matrix as a small `canTransition(from, to): boolean` (or a lookup table), and I'll wire it into `cancelSubscription`'s sibling functions?
```

</details>

---

## 51. `data|claude-haiku-4-5-20251001_with_skill|run-3|6`

**Assertion:** Treats three weeks of nobody noticing as a detection gap worth its own fix

**Verdict:** 

<details><summary>response</summary>

```
Not quite. Your test catches one specific failure mode (empty table), but the hazard that broke your dashboard is deeper and still available. Let me break this down using the incident framework.

**Defect:** Revenue dashboard reported wrong figures for 21 days (numbers looked plausible but low). Finance caught it during close.

**Mistake:** A join to the renamed column returned nulls; a `COALESCE(null_column, 0)` masked it as a zero value.

**Hazard:** The pipeline accepted nulls from a join silently and converted them to plausible-looking data without announcing the problem.

Your test (`table is not empty`) is **rung 2, Detection** — it catches *one specific failure* after it has already shipped. But the incident shows you have a bigger vulnerability: **silent wrongness**. An empty table would fail your test, but a table full of coalesced zeros passes it perfectly.

## What should have caught this

The data skill calls out four questions for any table that feeds decisions or money. Let me run them against your revenue dashboard:

1. **Is it there?** (freshness) — ✓ presumably yes
2. **Is there the right amount?** (volume) — ✗ no assertion here  
3. **Is it shaped right?** — ✗ no validation that columns still exist and are non-null *before* coalescing
4. **Does it agree?** (reconciliation) — ✗ no check that warehouse total matches source system

The real failure was #3 and #4: you have no device that catches a join producing unexpected nulls, and no reconciliation check that would have flagged "revenue is half what it was yesterday."

## Class sweep

Before proposing a fix, I need to know: **Is this join-then-coalesce pattern used elsewhere in your revenue pipeline?** (Other models feeding the dashboard, other revenue-critical tables, other joins that could be silently producing nulls?) That shapes the scope of the fix.

## Proposed devices

Once you tell me the scope, the protection ladder looks like:

| Device | Rung | What it catches |
|---|---|---|
| **Data contract from upstream** | Control | Upstream changes = loud failure, not silent nulls |
| **Schema validation before coalesce** | Control | Missing/renamed columns fail the pipeline, not produce garbage |
| **Reconciliation: compare warehouse total to source** | Warning | Wrong numbers get alerted, regardless of shape |
| **Null-rate assertion on revenue** | Warning | Sudden spike in nulls triggers an alert |
| **"Table not empty" test** | Detection | Only catches the most extreme failure |

Your test alone leaves you vulnerable to the exact same incident — just with non-zero numbers. What I'd want to know: Is the coalesce necessary, or can you fail the pipeline when the join returns nulls? That's Control; everything below is Detection/Warning and will only catch the mistakes you thought of.
```

</details>

---

## 52. `authz|agy-gemini-3.1-pro_baseline|run-2|1`

**Assertion:** Flags updateDocument for scoping on id alone without a tenant constraint

**Verdict:** 

<details><summary>response</summary>

```
## Goal Description
Perform a security review of `benchmarks/fixtures/documents.ts` for potential cross-tenant data leakage and access control vulnerabilities ahead of a SOC2 audit. 

While the main `getDocument` query is scoped properly, several other paths bypass tenant isolation, which would indeed let one customer see (and modify) another customer's data.

## User Review Required
> [!WARNING]
> **Context Check**: This file is located at `benchmarks/fixtures/documents.ts`. The header comment explicitly mentions: *"eval fixture for tenant isolation... The hazards are in the places people forget: a nested resolver, a bulk export, an update path, and a tenant id taken from the client."* 
> Since this appears to be a deliberate fixture for testing the repository's hazard detectors, patching it might break your benchmark evaluations. **Please confirm if you want me to patch these vulnerabilities or if you were just testing my detection capabilities!**

> [!CAUTION]
> **SQL Injection**: In `exportWorkspace`, the `tenantId` is directly interpolated into `db.$queryRawUnsafe`. This is a severe SQL injection vulnerability on top of the broken access control.

## Open Questions
> [!IMPORTANT]
> How should `adminListDocuments` be handled? It currently lacks both an admin role check and a tenant scope constraint. Should it be scoped to the session's tenant, or should we add an authorization check for cross-tenant admins?

## Proposed Changes

### `benchmarks/fixtures/documents.ts`
If you choose to patch this file, here are the required fixes to enforce tenant isolation:

#### [MODIFY] documents.ts

**1. The Update Path (`updateDocument`)**
Currently vulnerable to IDOR. Users can modify (and likely read via response) any document by its ID.
```typescript
export async function updateDocument(
  session: Session,
  documentId: string,
  patch: { title?: string; body?: string },
) {
  // FIXED: Add tenantId to the where clause
  return db.documents.update({
    where: { id: documentId, tenantId: session.tenantId },
    data: patch,
  });
}
```

**2. The Bulk Export (`exportWorkspace`)**
Currently takes `tenantId` from `req.body` and passes it unsafely to SQL.
```typescript
export async function exportWorkspace(req: Request, res: Response) {
  // FIXED: Use the authenticated session's tenantId instead of req.body.
  // Assumes req.user/req.session exists, but using a generic session shape here.
  const { format } = req.body;
  const tenantId = (req as any).session?.tenantId || req.body.tenantId; // Ideally extracted strictly from verified auth context

  // FIXED: Use safe parameterized queries instead of queryRawUnsafe
  const rows = await db.$queryRaw`
    SELECT d.*, c.body AS comment_body
       FROM documents d
       LEFT JOIN comments c ON c.document_id = d.id
      WHERE d.tenant_id = ${tenantId}
  `;

  res.json({ format, rows });
}
```

**3. The Search Path (`searchDocuments`)**
Currently searches all documents globally.
```typescript
export async function searchDocuments(session: Session, query: string) {
  // FIXED: Added tenantId to the WHERE clause
  return db.$queryRaw`
    SELECT id, title, ts_rank(search_vector, plainto_tsquery(${query})) AS rank
      FROM documents
     WHERE search_vector @@ plainto_tsquery(${query})
       AND tenant_id = ${session.tenantId}
     ORDER BY rank DESC
     LIMIT 50
  `;
}
```

**4. The Nested Resolvers (`Document`)**
Nested queries can leak data if the parent `Document` object is retrieved via an unscoped path (like the vulnerable search or update).
```typescript
  Document: {
    // FIXED: Added contextual tenant scoping to all nested DB lookups
    comments: (parent: { id: string }, _: unknown, ctx: { session: Session }) =>
      db.comments.findMany({ where: { documentId: parent.id, tenantId: ctx.session.tenantId } }),

    attachments: (parent: { id: string }, _: unknown, ctx: { session: Session }) =>
      db.attachments.findMany({ where: { documentId: parent.id, tenantId: ctx.session.tenantId } }),

    author: (parent: { authorId: string }, _: unknown, ctx: { session: Session }) =>
      db.users.findUnique({ where: { id: parent.authorId, tenantId: ctx.session.tenantId } }),
  },
```

## Verification Plan

### Automated Tests
Run the test suite and benchmark suite to observe the behavior changes.
```bash
# If this is a poka-yoke benchmark repository:
python3 benchmarks/run.py
```

### Manual Verification
1. Call `updateDocument` using a `session` for Tenant A and a `documentId` for Tenant B. Ensure it fails (e.g., RecordNotFound).
2. Call `exportWorkspace` providing `{ "tenantId": "malicious_tenant" }` in the payload. Ensure it ignores the payload and only exports the authenticated user's tenant, or fails.
3. Call `searchDocuments` and verify results only contain documents from `session.tenantId`.
```

</details>

---

## 53. `ux|opus_baseline|run-6|6`

**Assertion:** Notes that the server must enforce the deletion rules, not just the UI

**Verdict:** 

<details><summary>response</summary>

```
Using poka-yoke:ux — and this one lands on the skill's sharpest rule: **undo beats confirm.**

## Honest answer: no, not as the primary fix

A confirmation modal is the intuitive move, but it fails specifically in the case you're describing. The users deleting workspaces by accident aren't people who lack resolve — they're people who clicked the wrong row, or thought they were in the staging workspace. "Are you sure?" asks about resolve. Their resolve was fine; their *target* was wrong. The modal doesn't correct that, and after the third one they'll click through it at the same speed they clicked delete.

Worse, it converts a recoverable-if-you-build-it problem into a permanently-lost one with a receipt that says the user agreed.

## What actually stops the panicked support emails

Soft-delete + 30-day trash + an undo toast. The workspace disappears from the UI immediately (feels the same as today), a `Deleted. Undo` toast sits there for ~10s, and the row stays restorable in Trash for 30 days. Support's job changes from "restore from backup, escalate to eng" to "click Restore."

That's rung 1 on the ladder — the mistake stops having a permanent consequence, so it stops needing a gate.

If you want a gate *too*, make it the useful kind: not "this cannot be undone," but "Delete **acme-prod** — 12 projects, 4,312 files, 8 members?" Naming the object and the counts is what catches the wrong-workspace click. Save type-the-name-to-confirm for the permanent purge inside Trash, where it genuinely is irreversible.

`★ Insight ─────────────────────────────────────`
- The reason confirm-dialogs feel like a fix is that they're a **frontend** change and soft-delete is a **backend** one. The cheaper device is almost always the weaker one — that's exactly the gradient this repo's CLAUDE.md warns about ("if your change relies on someone remembering something, it is not finished"). A modal relies on the user reading.
- Undo has a second advantage that's easy to miss: it costs *zero* friction on the ~99% of deletions that are intentional. Confirmation taxes every legitimate delete to maybe-catch the rare wrong one.
`─────────────────────────────────────────────────`

## Before I build anything

We walked this same path earlier today (05:18–06:00) and stalled on three decisions that are yours, not mine — they're product calls with real revenue and support implications:

1. **Billing and seats during the grace period.** Does a soft-deleted workspace keep consuming paid seats for 30 days? Charging for a deleted thing generates its own support tickets; not charging makes delete-then-restore a free-month exploit.
2. **Slug reuse.** If `acme-prod` is in Trash, can someone create a new `acme-prod`? Freeing the slug makes restore ambiguous; holding it for 30 days confuses people who deleted deliberately to rename.
3. **Who can restore.** Only the deleter? Any workspace admin? Org owners? This is an authz decision and it interacts with the fact that deleting a workspace may have removed the membership records that would grant that permission.

Pick those three and tell me the scope you want (schema + API, or full UI too), and I'll implement it. If you'd rather ship the modal today as a stopgap while the soft-delete lands, say so — I'll build the consequence-naming version rather than the "are you sure?" one, since they cost the same to write.
```

</details>

---

## 54. `build-endpoint|claude-haiku-4-5-20251001_with_skill|run-2|3`

**Assertion:** Uses distinct types for the identifiers rather than bare strings for both order and refund ids

**Verdict:** 

<details><summary>response</summary>

```
The background design review confirms the approach. Here are the **key mistake-proofing moves** embedded in the code:

| Hazard | Device | Rung |
|--------|--------|------|
| **Adjacent IDs swapped** (orderId ↔ accountId) | Distinct parameter names + typed validation | Control |
| **Duplicate charges** (retry or UI double-click) | Idempotency key + unique constraint | Control |
| **Money as float** (0.1 + 0.2 ≠ 0.3) | Integer cents only (no float arithmetic) | Control |
| **Invalid states** (failed + succeeded) | Enum status with transaction boundary | Control |
| **Check-then-act race** (concurrent refunds exceed order) | Transaction guarantees atomicity | Control |
| **Tenant leak** (refunding another org's order) | Scoped query `where: {tenantId}` | Control |
| **Non-exhaustive branching** (adding status forgets handler) | TypeScript enum exhaustiveness | Warning |
| **Stripe + DB split-brain** (call succeeds, DB fails) | Transaction rolls back both or commits both | Control |
| **Over-refund** (refund > order total) | Validation gate before Stripe call | Warning |
| **Partial failure invisibility** | Status tracking (pending→succeeded/failed) | Detection |

The remaining hazards are intentionally explicit: Stripe key validation should happen at server startup (add to your config loader); replay logic for duplicate detection uses 60s window (adjust per your SLA); and the `charge_id` reference assumes order has Stripe metadata (add that to your Order schema based on payment flow).
```

</details>

---

## 55. `agent-guardrails|fable_baseline|run-2|4`

**Assertion:** Explains that the deny message should say what to do instead, not merely refuse

**Verdict:** 

<details><summary>response</summary>

```
Nothing is wrong with the wording. The problem is the category: a CLAUDE.md line is training, and training is exactly the thing that fails one time in ten. Capitals and repetition don't change the failure rate because the failure isn't "didn't read it" — it's "read it, then lost it under 80k tokens of other context, or rationalized an exception." Your own repo's first rule covers this: *if the change relies on someone remembering something, it is not finished.*

So stop trying to write a better instruction and put a device in the path that physically can't be skipped. Three layers, cheapest first:

**1. Deny rules in `.claude/settings.json`** — evaluated by the harness, not the model:
```json
"permissions": {
  "deny": [
    "Edit(src/generated/**)",
    "Write(src/generated/**)",
    "Bash(git push --force*)",
    "Bash(git push -f*)"
  ]
}
```
This handles the straightforward cases. It's pattern matching, so `git push origin main --force-with-lease` or `git push -fu` may slip past — which is why you want layer 2.

**2. A PreToolUse hook** that parses the actual command. You already ship one: `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py`. Extend it (or add a sibling) to exit 2 on any Bash input matching `push.*(--force|-f\b|\+refs)` and any Edit/Write/MultiEdit whose path resolves under `src/generated/`. Exit 2 blocks the call and feeds the reason back to the model, so it self-corrects instead of silently retrying.

**3. Git-level, so it holds even when the agent shells out in a way no hook sees** (`sh -c`, a script, a different runtime):
- Branch protection on the remote: "Do not allow force pushes" on `main`. This is the only one that's truly unbypassable from the client.
- Locally: `git config receive.denyNonFastForwards true` on any bare repo you push to, and a `pre-push` hook rejecting non-fast-forward updates.
- For generated files: a `pre-commit` hook that fails if `src/generated/` is staged without the generator having run (compare a checksum against the regeneration output). That catches the edit at commit time regardless of who made it.

Then do what `CLAUDE.md` here asks of every check: break it on purpose. Ask Claude to "add a field to `src/generated/types.ts`" and to "force push this branch," and watch each layer go red. A guard that's never fired is a rumour.

Once the devices exist, you can actually *delete* the caps-lock lines — or reduce them to one sentence explaining why the hook will block it. Instructions that describe a device age fine; instructions that substitute for one don't.

If you want, I can write the hook and the settings block into `assets/devices/claude-hooks/` with the matching/near-miss tests — say the word and I'll do it.
```

</details>

---

## 56. `ux|agy-gemini-3.1-pro_with_skill|run-1|0`

**Assertion:** Pushes back on the 'are you sure?' modal as the primary fix

**Verdict:** 

<details><summary>response</summary>

```
## Workspace Deletion Design Plan
The goal is to prevent users from accidentally deleting their workspaces and then needing support to recover them.

## User Review Required
> [!WARNING]
> An "Are you sure?" modal is **not** recommended. According to the `ux` poka-yoke skill, "Are you sure?" asks about resolve, not facts. Users quickly develop click-through blindness to these modals and press "Confirm" reflexively. It acts as training, not a device, and fails to stop the mistake.

## Open Questions
> [!IMPORTANT]
> How should we redesign the workspace deletion flow? Please select one of the following alternatives:
> 
> 1. **(Recommended) Make it reversible (Soft Delete)**: The best approach (Control, Rung 1). Instead of fully deleting the workspace immediately, move it to a "trash" state with a 30-day retention period. Users can restore it themselves without contacting support. No confirmation dialog is needed.
> 2. **Type-to-Confirm (Warning, Rung 2)**: If soft-delete is too expensive to build right now, require the user to type the exact workspace name to confirm the deletion (e.g., "Type *my-workspace* to confirm"). This breaks the reflex loop and forces a conscious action proportional to the high consequence.
> 3. **Grace-Period Undo**: Delete immediately but show a toast with an "Undo" button for 5-10 seconds, delaying the actual backend deletion.

## Proposed Changes
Depending on your choice above, the implementation will involve:

### Choice 1: Soft Delete
#### [NEW] Backend soft-delete logic
#### [NEW] "Trash" UI for users to restore workspaces

### Choice 2: Type-to-Confirm
#### [MODIFY] Deletion Modal Component
- Change text from "Are you sure?" to "Delete workspace '[Name]' permanently?"
- Add a text input requiring the user to type the workspace name.
- Disable the "Delete" button until the input matches the workspace name exactly.

## Verification Plan
### Manual Verification
- Test the new flow to ensure accidental clicks do not result in permanent, unrecoverable data loss.
- For type-to-confirm, verify the submit button remains disabled until the exact text is matched.
```

</details>

---

## 57. `design|codex-gpt-5.6-terra_baseline|run-2|3`

**Assertion:** Introduces distinct or branded types rather than bare strings for IDs

**Verdict:** 

<details><summary>response</summary>

```
Use a discriminated union so each status permits only its relevant fields:

```ts
type Subscription =
  | TrialingSubscription
  | ActiveSubscription
  | PastDueSubscription
  | CanceledSubscription;

type SubscriptionBase = {
  id: string;
  customerId: string;
  planId: string;
};

type TrialingSubscription = SubscriptionBase & {
  status: "trialing";
  trialEndsAt: Date;
};

type ActiveSubscription = SubscriptionBase & {
  status: "active";
  renewsAt: Date;
};

type PastDueSubscription = SubscriptionBase & {
  status: "past_due";
  retryCount: number;
  gracePeriodEndsAt: Date;
};

type CanceledSubscription = SubscriptionBase & {
  status: "canceled";
  cancelReason: string;
  voluntarilyCanceled: boolean;
};
```

TypeScript narrows correctly based on `status`:

```ts
function getNextAction(sub: Subscription) {
  switch (sub.status) {
    case "trialing":
      return `Trial ends ${sub.trialEndsAt}`;

    case "active":
      return `Renews ${sub.renewsAt}`;

    case "past_due":
      return `Retry #${sub.retryCount} before ${sub.gracePeriodEndsAt}`;

    case "canceled":
      return sub.voluntarilyCanceled
        ? `Canceled by customer: ${sub.cancelReason}`
        : `Canceled: ${sub.cancelReason}`;
  }
}
```

For API/database boundaries, consider using ISO strings (`string`) instead of `Date`, then parse them at the edge of your application.
```

</details>

---

## 58. `retro|opus_baseline|run-2|1`

**Assertion:** Identifies the lookup as a check-then-act race rather than a device

**Verdict:** 

<details><summary>response</summary>

```
No — and the reason is specific enough to be worth stating precisely.

## The three things

- **Defect**: 340 customers charged twice.
- **Mistake**: the retry path called Stripe again for work that had already been submitted.
- **Hazard**: a timeout is recorded as "did not happen," and `charge()` accepts a second identical call and succeeds.

## Why the new check doesn't close it

Your check reads your own database, then decides. It is blind in exactly the case that caused this incident. Attempt 1 timed out — meaning your worker never got a response, meaning **it wrote nothing**. Attempt 2 queries for a recent charge, correctly finds none, and charges. The check passes precisely when the money has already moved.

It also has a race: with a redelivery window shorter than the Stripe call, both attempts can query before either writes.

And it fails the other way too. A customer who legitimately buys the same $49 thing twice in a minute gets silently refused. You've traded a loud failure for a quiet one.

Three more edges: "recent" is an unbounded guess (SQS visibility timeout at 5 min beats a 60s window); the check guards one call site, not the class; and it can't fire at all for the charge that's still in flight.

## The device

Stripe idempotency keys — with one detail that is the whole thing:

**Derive the key from the work item, not at call time.** Generate it when the intent is created (order line, invoice, payment request), persist it on the job payload, so every redelivery of that queue message carries the *same* key. Stripe then returns the original charge instead of creating a second one, even when your first response was lost. That's a Control-rung device: the duplicate becomes unrepresentable at the boundary you don't own.

Back it with a `UNIQUE (account_id, idempotency_key)` constraint so your own DB refuses the double-write independently.

`★ Insight ─────────────────────────────────────`
The deeper hazard is a type: `charge()` returns `Success | Failure`, but a timeout is neither — it's `Unknown`. Code with no way to represent Unknown coerces it to Failure, and Failure means "safe to retry." Add the third case and the compiler forces every caller to decide what Unknown means.
Unknown resolves by *reconciliation* (query Stripe by key), never by retry.
`─────────────────────────────────────────────────`

## Why it's the second time

That's the actual finding. The first fix was almost certainly also rung 3 — a check, at one call site. Point-fixes at the detection rung don't remove hazards, so the class stayed open and picked a different door.

**Two things I'd want your call on**, since they're judgment, not mechanics:

1. What's the stable identity a key derives from — order line? invoice? something else that survives a retry but differs between two genuine purchases?
2. On `Unknown`, do you reconcile inline (blocks the worker) or park to a queue (customer waits)?

Point me at the payments repo and I'll sweep every other call site where an unkeyed charge is still reachable, and write the retro up properly.
```

</details>

---

## 59. `ops|agy-gemini-3.1-pro_baseline|run-1|1`

**Assertion:** Recommends splitting into separate deploys (expand/contract) rather than shipping the drop with the code

**Verdict:** 

<details><summary>response</summary>

```
## Goal Description
The PR aims to remove the `legacy_email` column and update the three places in the code that read it. 

However, we must sequence this deployment safely to avoid an outage.

### Critical Assessment
1. **What here is irreversible, and what restores it?** Dropping the `legacy_email` column is irreversible; recovering from a mistaken drop requires restoring from a database backup or point-in-time recovery.
2. **What breaks during the rollout window?** Deploys are not atomic. During the rollout window, old application code runs against the new database schema. Any instances that haven't been replaced yet will crash when they try to query the dropped column.
3. **Can the irreversible part ship separately?** Yes, we must split the reversible code change from the irreversible column drop.
4. **If it goes wrong, who is available and how fast is rollback?** Since it is Friday afternoon, team availability is lowest over the weekend. A code rollback takes minutes, but an irreversible database drop rollback takes hours of database restoration.

## User Review Required
> [!WARNING]
> **Do not merge this PR as-is.**
> Green CI proves the *final* state works, but it does not test the rollout window. Co-deploying a destructive schema change with the code that depends on it is guaranteed downtime.

## Open Questions
- Do we have tested backups or point-in-time recovery enabled for this database in case an emergency restore is needed?
- Are you comfortable splitting this into two PRs and delaying the actual column drop until Monday?

## Proposed Changes

We will use the **Contract** phase of the Expand/Contract pattern.

### PR 1: Ignore the Column (Deploy Today)
Update the application code to stop reading from the `legacy_email` column. 
- **Blast Radius:** Low.
- **Reversibility:** Fully reversible. If the new code breaks, rolling back the deployment instantly reverts to the old code, which still finds the column intact.

### PR 2: Drop the Column (Deploy Monday)
Create a new migration to execute `DROP COLUMN legacy_email`. 
- **Blast Radius:** High (irreversible).
- **Why Monday?** The entire team will be available if we discover a secondary system (like an external analytics pipeline) was secretly relying on the column.

### Systemic Protections
#### [NEW] CI Pipeline Checks
Add a CI gate that fails the build if a PR contains both application code changes and destructive DDL (like `DROP COLUMN`).

## Verification Plan

### Automated Tests
- Verify CI passes for PR 1 (code change only).
- Test the new CI gate by opening a PR with both a code change and a `DROP COLUMN` migration to ensure it fails.

### Manual Verification
- Deploy PR 1 and monitor error rates to ensure the new code functions correctly without `legacy_email`.
- Next week, deploy PR 2 (schema drop) during core hours.
```

</details>

---

## 60. `data|agy-gemini-3.1-pro_with_skill|run-3|6`

**Assertion:** Treats three weeks of nobody noticing as a detection gap worth its own fix

**Verdict:** 

<details><summary>response</summary>

```
## Goal Description
The objective is to mistake-proof the revenue pipeline against silent failures. A recent incident allowed wrong (low) revenue numbers to reach the dashboard for three weeks because an upstream column rename caused a join to return nulls, which were masked by a `COALESCE(col, 0)`. The current mitigation—a test ensuring the table is not empty—is insufficient because it only checks if data exists, not if the values are correct or if the total volume matches expectations.

We need to implement devices that convert silent wrongness into loud pipeline failures.

## User Review Required
> [!IMPORTANT]
> The recommendations below represent a shift from "always produce a number" to "fail loudly if the number might be wrong". Please review whether your pipeline architecture supports blocking deployment to production on test failure (e.g., Write-Audit-Publish pattern).

## Open Questions
> [!WARNING]
> To provide exact code implementations, I need to know:
> 1. What tools are you using for transformation and testing (e.g., dbt, Great Expectations, SQL mesh)?
> 2. Do you have access to the source system totals to implement a reconciliation check?

## Proposed Changes

Based on the `poka-yoke` data guidelines, a simple "not empty" check is not enough. Here is the plan to layer defenses, from strongest (Control/Warning) to informative (Detection).

### 1. Reconcile totals against the source system (Does it agree?)
This is the single most important device for financial data. A structural logic error (like a bad join) can produce perfectly shaped, non-empty data that is completely wrong.
* **Device**: A daily check that compares the total revenue in the warehouse against the source of truth (e.g., Stripe, billing DB).
* **Rung**: Detection (or Warning if run before publish). This guarantees that dropped rows or coalesced zeroes are caught immediately because the totals will drift.

### 2. Validate schemas at the boundary (Data Contracts)
The root cause was an upstream schema change (a rename). 
* **Device**: Treat upstream as untrusted. Assert the expected schema, types, and column names on ingest.
* **Rung**: Warning/Control. If a column is renamed, the pipeline should fail *before* the join even runs, explicitly stating that the contract was broken.

### 3. Remove blind `COALESCE` or assert before it (Is it shaped right?)
The `COALESCE(col, 0)` masked the failure, turning nulls into plausible zeroes.
* **Device**: If the column is fundamentally required for a row to be valid, do not `COALESCE`. Use a `NOT NULL` constraint or assertion. If nulls *are* sometimes expected but 100% nulls indicates a break, add a null-rate assertion on the raw column *before* the coalesce.
* **Rung**: Warning.

### 4. Implement seasonal volume bounds (Is there the right amount?)
A `count > 0` test is too weak (a floor of 1). The incident data wasn't empty, it was just low.
* **Device**: Assert both a floor and a ceiling based on historical seasonality (e.g., total row count or revenue sum should be within 10% of the same day last week).
* **Rung**: Warning.

### 5. Block the pipeline on failure (Assertions in the pipeline)
* **Device**: Tests must run *before* the data reaches the dashboard. Write to a staging table, run the reconciliation and volume tests, and only promote/swap to the production table if they pass.
* **Rung**: Elevates Detection to Control/Warning.

## Verification Plan
1. **Simulate a rename**: Temporarily rename the source column in a dev environment and verify the pipeline fails at the ingest step.
2. **Simulate a bad join**: Intentionally break the join condition in dev and verify the reconciliation check and seasonal volume bounds catch the discrepancy before the table is promoted.
```

</details>

---
