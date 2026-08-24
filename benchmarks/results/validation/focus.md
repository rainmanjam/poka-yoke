# Focused validation worksheet

18 assertion verdicts: every item the three graders split on, plus 8 they agreed on, shuffled together. **Which is which is not shown, and should not be guessed at** — knowing an item was contested is the hint that would turn this into a measurement of how hard you looked.

Read the response, decide whether the assertion holds, write `PASS`, `FAIL` or `UNCLEAR` on the verdict line. `UNCLEAR` is a finding about the assertion, not about you: an assertion three frontier models split on is usually ambiguous.

---

## 1. `data|opus_baseline|run-1|6`

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

## 2. `ops|claude-haiku-4-5-20251001_baseline|run-1|5`

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

## 3. `authz|agy-gemini-3.1-pro_baseline|run-2|1`

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

## 4. `data|codex-gpt-5.6-terra_with_skill|run-1|2`

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

## 5. `build-form|codex-gpt-5.6-terra_baseline|run-2|0`

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

## 6. `data|claude-haiku-4-5-20251001_with_skill|run-3|6`

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

## 7. `build-endpoint|agy-gemini-3.1-pro_with_skill|run-1|6`

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

## 8. `retro|codex-gpt-5.6-terra_baseline|run-1|4`

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

## 9. `authz|agy-gemini-3.1-pro_with_skill|run-1|7`

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

## 10. `llm|claude-haiku-4-5-20251001_baseline|run-2|1`

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

## 11. `audit|fable_with_skill|run-3|2`

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

## 12. `retro|opus_with_skill|run-2|6`

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

## 13. `agent-guardrails|opus_with_skill|run-2|2`

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

## 14. `data|agy-gemini-3.1-pro_with_skill|run-3|6`

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

## 15. `retro|agy-gemini-3.1-pro_baseline|run-1|8`

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

## 16. `retro|opus_baseline|run-1|1`

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

## 17. `data|claude-sonnet-5_with_skill|run-1|7`

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

## 18. `audit|claude-sonnet-5_with_skill|run-5|3`

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
