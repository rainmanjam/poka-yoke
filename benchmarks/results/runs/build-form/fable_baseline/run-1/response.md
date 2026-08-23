Here's the complete implementation. Assumptions: TanStack Query for data, documents are soft-deleted to a trash (so Delete is recoverable for 30 days), and the list API accepts a `filter` object that the bulk endpoint can also accept.

```tsx
// documents/types.ts
export type DocumentId = string & { readonly __brand: "DocumentId" };

export interface Document {
  id: DocumentId;
  title: string;
  updatedAt: string;
  ownerName: string;
}

export interface DocumentFilter {
  search?: string;
  ownerId?: string;
}

/**
 * Selection is a discriminated union, not a Set<string>.
 * "Select all N matching" with N in the thousands cannot be a list of ids —
 * the list is paginated and the client never holds them all. So the server
 * receives the *filter* plus the count the user saw, and refuses if they diverge.
 */
export type Selection =
  | { mode: "none" }
  | { mode: "ids"; ids: ReadonlySet<DocumentId> }
  | { mode: "all-matching"; filter: DocumentFilter; expectedTotal: number; except: ReadonlySet<DocumentId> };

export type BulkAction = "archive" | "trash";

export interface BulkRequest {
  action: BulkAction;
  target:
    | { kind: "ids"; ids: DocumentId[] }
    | { kind: "filter"; filter: DocumentFilter; expectedTotal: number; exceptIds: DocumentId[] };
  idempotencyKey: string;
}

export interface BulkResult {
  batchId: string;      // handle for undo
  affected: number;
}
```

```ts
// documents/api.ts
import type { BulkRequest, BulkResult, Document, DocumentFilter } from "./types";

export interface Page<T> { items: T[]; total: number; page: number; pageSize: number }

export async function listDocuments(filter: DocumentFilter, page: number): Promise<Page<Document>> {
  const qs = new URLSearchParams({ ...stringify(filter), page: String(page), pageSize: "50" });
  const res = await fetch(`/api/documents?${qs}`);
  if (!res.ok) throw new Error(`list failed: ${res.status}`);
  return res.json();
}

export async function bulkMutate(req: BulkRequest): Promise<BulkResult> {
  const res = await fetch(`/api/documents/bulk`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": req.idempotencyKey },
    body: JSON.stringify(req),
  });
  if (res.status === 409) {
    // Server compared expectedTotal with the live count and they differed.
    throw new CountMismatchError(await res.json());
  }
  if (!res.ok) throw new Error(`bulk ${req.action} failed: ${res.status}`);
  return res.json();
}

export async function undoBulk(batchId: string): Promise<void> {
  const res = await fetch(`/api/documents/bulk/${batchId}/undo`, { method: "POST" });
  if (!res.ok) throw new Error(`undo failed: ${res.status}`);
}

export class CountMismatchError extends Error {
  constructor(public detail: { expected: number; actual: number }) {
    super(`Expected ${detail.expected} documents, server now has ${detail.actual}`);
  }
}

function stringify(o: object) {
  return Object.fromEntries(Object.entries(o).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]));
}
```

```ts
// documents/useSelection.ts
import { useCallback, useEffect, useMemo, useState } from "react";
import type { Document, DocumentFilter, DocumentId, Selection } from "./types";

export function useSelection(filter: DocumentFilter, pageItems: Document[], total: number) {
  const [selection, setSelection] = useState<Selection>({ mode: "none" });

  // A selection is only meaningful against the filter it was made under.
  // Changing the filter silently re-targets "all matching" — so we clear instead.
  const filterKey = JSON.stringify(filter);
  useEffect(() => { setSelection({ mode: "none" }); }, [filterKey]);

  const isSelected = useCallback((id: DocumentId) => {
    switch (selection.mode) {
      case "none": return false;
      case "ids": return selection.ids.has(id);
      case "all-matching": return !selection.except.has(id);
    }
  }, [selection]);

  const toggle = useCallback((id: DocumentId) => {
    setSelection((s) => {
      if (s.mode === "all-matching") {
        const except = new Set(s.except);
        except.has(id) ? except.delete(id) : except.add(id);
        return { ...s, except };
      }
      const ids = new Set(s.mode === "ids" ? s.ids : []);
      ids.has(id) ? ids.delete(id) : ids.add(id);
      return ids.size === 0 ? { mode: "none" } : { mode: "ids", ids };
    });
  }, []);

  const togglePage = useCallback(() => {
    setSelection((s) => {
      const pageIds = pageItems.map((d) => d.id);
      const allOnPageSelected = pageIds.every(isSelected);
      if (s.mode === "all-matching") {
        const except = new Set(s.except);
        pageIds.forEach((id) => (allOnPageSelected ? except.add(id) : except.delete(id)));
        return { ...s, except };
      }
      const ids = new Set(s.mode === "ids" ? s.ids : []);
      pageIds.forEach((id) => (allOnPageSelected ? ids.delete(id) : ids.add(id)));
      return ids.size === 0 ? { mode: "none" } : { mode: "ids", ids };
    });
  }, [pageItems, isSelected]);

  const selectAllMatching = useCallback(() => {
    setSelection({ mode: "all-matching", filter, expectedTotal: total, except: new Set() });
  }, [filter, total]);

  const clear = useCallback(() => setSelection({ mode: "none" }), []);

  const count = useMemo(() => {
    switch (selection.mode) {
      case "none": return 0;
      case "ids": return selection.ids.size;
      case "all-matching": return selection.expectedTotal - selection.except.size;
    }
  }, [selection]);

  const pageState = useMemo(() => {
    const n = pageItems.filter((d) => isSelected(d.id)).length;
    return n === 0 ? "none" : n === pageItems.length ? "all" : "some";
  }, [pageItems, isSelected]);

  return { selection, count, pageState, isSelected, toggle, togglePage, selectAllMatching, clear };
}
```

```tsx
// documents/useBulkAction.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { bulkMutate, undoBulk } from "./api";
import type { BulkAction, BulkRequest, Selection } from "./types";

export function toRequest(action: BulkAction, s: Selection, idempotencyKey: string): BulkRequest {
  switch (s.mode) {
    case "none": throw new Error("no selection"); // unreachable: bar is not rendered
    case "ids": return { action, target: { kind: "ids", ids: [...s.ids] }, idempotencyKey };
    case "all-matching":
      return {
        action,
        target: { kind: "filter", filter: s.filter, expectedTotal: s.expectedTotal, exceptIds: [...s.except] },
        idempotencyKey,
      };
  }
}

export function useBulkAction(onDone: (r: { batchId: string; affected: number; action: BulkAction }) => void) {
  const qc = useQueryClient();
  // One key per *selection attempt*, minted when the bar first arms, so a
  // double-click, a retry, or a refresh-and-resubmit all collapse to one mutation.
  const keyRef = useRef<string | null>(null);
  const keyFor = () => (keyRef.current ??= crypto.randomUUID());

  const mutation = useMutation({
    mutationFn: ({ action, selection }: { action: BulkAction; selection: Selection }) =>
      bulkMutate(toRequest(action, selection, keyFor())),
    onSuccess: (result, { action }) => {
      keyRef.current = null;
      qc.invalidateQueries({ queryKey: ["documents"] });
      onDone({ ...result, action });
    },
    onError: () => { keyRef.current = null; },
  });

  const undo = useMutation({
    mutationFn: undoBulk,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });

  return { run: mutation.mutate, isRunning: mutation.isPending, error: mutation.error, undo: undo.mutate };
}
```

```tsx
// documents/BulkActionsBar.tsx
import { useState } from "react";
import { CountMismatchError } from "./api";
import type { BulkAction, Selection } from "./types";

interface Props {
  selection: Selection;
  count: number;
  total: number;
  pageSize: number;
  isRunning: boolean;
  error: unknown;
  onSelectAllMatching: () => void;
  onClear: () => void;
  onRun: (action: BulkAction) => void;
}

const LARGE = 200; // above this, Trash requires typing the count

export function BulkActionsBar(p: Props) {
  const [confirmText, setConfirmText] = useState("");
  if (p.selection.mode === "none") return null;

  const showSelectAll = p.selection.mode === "ids" && p.count === Math.min(p.pageSize, p.total) && p.total > p.pageSize;
  const needsTyped = p.count >= LARGE;
  const trashArmed = !needsTyped || confirmText === String(p.count);

  return (
    <div
      role="region"
      aria-label="Bulk actions"
      className="sticky top-0 z-10 flex flex-wrap items-center gap-3 rounded-md border border-slate-200 bg-slate-50 px-4 py-2 text-sm shadow-sm"
    >
      <span className="font-medium tabular-nums" aria-live="polite">
        {p.count.toLocaleString()} of {p.total.toLocaleString()} selected
        {p.selection.mode === "all-matching" && " (all matching)"}
      </span>

      {showSelectAll && (
        <button type="button" onClick={p.onSelectAllMatching} className="text-blue-700 underline-offset-2 hover:underline">
          Select all {p.total.toLocaleString()} matching
        </button>
      )}

      <button type="button" onClick={p.onClear} className="text-slate-600 hover:text-slate-900">
        Clear
      </button>

      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          disabled={p.isRunning}
          onClick={() => p.onRun("archive")}
          className="rounded border border-slate-300 bg-white px-3 py-1 hover:bg-slate-100 disabled:opacity-50"
        >
          Archive {p.count.toLocaleString()}
        </button>

        {/* Destructive control: visually separated, never primary, never default focus. */}
        <span className="mx-2 h-5 w-px bg-slate-300" aria-hidden />

        {needsTyped && (
          <label className="flex items-center gap-2 text-slate-700">
            <span>Type <b className="tabular-nums">{p.count}</b> to enable Trash</span>
            <input
              inputMode="numeric"
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              className="w-20 rounded border border-slate-300 px-2 py-1 tabular-nums"
              aria-label={`Type ${p.count} to confirm`}
            />
          </label>
        )}

        <button
          type="button"
          disabled={p.isRunning || !trashArmed}
          aria-disabled={!trashArmed}
          onClick={() => { p.onRun("trash"); setConfirmText(""); }}
          className="rounded border border-red-300 bg-white px-3 py-1 text-red-700 hover:bg-red-50 disabled:opacity-50"
        >
          Move {p.count.toLocaleString()} to trash
        </button>
      </div>

      {p.error instanceof CountMismatchError && (
        <p role="alert" className="basis-full text-red-700">
          The list changed: you selected {p.error.detail.expected.toLocaleString()} but {p.error.detail.actual.toLocaleString()} now match.
          Nothing was changed. Clear the selection and re-select.
        </p>
      )}
      {p.error && !(p.error instanceof CountMismatchError) && (
        <p role="alert" className="basis-full text-red-700">Action failed; nothing was changed. Try again.</p>
      )}
    </div>
  );
}
```

```tsx
// documents/DocumentsTable.tsx
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { listDocuments } from "./api";
import { BulkActionsBar } from "./BulkActionsBar";
import { useBulkAction } from "./useBulkAction";
import { useSelection } from "./useSelection";
import type { BulkAction, DocumentFilter } from "./types";

const PAGE_SIZE = 50;
const UNDO_MS = 8000;

export function DocumentsTable({ filter }: { filter: DocumentFilter }) {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useQuery({
    queryKey: ["documents", filter, page],
    queryFn: () => listDocuments(filter, page),
    placeholderData: (prev) => prev,
  });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  const sel = useSelection(filter, items, total);
  const [toast, setToast] = useState<{ batchId: string; affected: number; action: BulkAction } | null>(null);
  const timer = useRef<number>();

  const bulk = useBulkAction((r) => {
    sel.clear();
    setToast(r);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), UNDO_MS);
  });
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const headerRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (headerRef.current) headerRef.current.indeterminate = sel.pageState === "some";
  }, [sel.pageState]);

  return (
    <div className="space-y-3">
      <BulkActionsBar
        selection={sel.selection}
        count={sel.count}
        total={total}
        pageSize={PAGE_SIZE}
        isRunning={bulk.isRunning}
        error={bulk.error}
        onSelectAllMatching={sel.selectAllMatching}
        onClear={sel.clear}
        onRun={(action) => bulk.run({ action, selection: sel.selection })}
      />

      <table className="w-full text-sm">
        <thead className="border-b border-slate-200 text-left text-slate-600">
          <tr>
            <th className="w-8 px-2 py-2">
              <input
                ref={headerRef}
                type="checkbox"
                aria-label="Select all on this page"
                checked={sel.pageState === "all" && items.length > 0}
                onChange={sel.togglePage}
                disabled={items.length === 0}
              />
            </th>
            <th className="px-2 py-2">Title</th>
            <th className="px-2 py-2">Owner</th>
            <th className="px-2 py-2">Updated</th>
          </tr>
        </thead>
        <tbody className={isLoading ? "opacity-50" : ""}>
          {items.map((d) => (
            <tr key={d.id} className={sel.isSelected(d.id) ? "bg-blue-50" : "hover:bg-slate-50"}>
              <td className="px-2 py-1.5">
                <input
                  type="checkbox"
                  aria-label={`Select ${d.title}`}
                  checked={sel.isSelected(d.id)}
                  onChange={() => sel.toggle(d.id)}
                />
              </td>
              <td className="px-2 py-1.5">{d.title}</td>
              <td className="px-2 py-1.5">{d.ownerName}</td>
              <td className="px-2 py-1.5 tabular-nums">{new Date(d.updatedAt).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <nav className="flex items-center justify-between text-sm text-slate-600">
        <span>Page {page} of {Math.max(1, Math.ceil(total / PAGE_SIZE))}</span>
        <div className="flex gap-2">
          <button type="button" disabled={page === 1} onClick={() => setPage((p) => p - 1)} className="rounded border px-2 py-1 disabled:opacity-40">Prev</button>
          <button type="button" disabled={page * PAGE_SIZE >= total} onClick={() => setPage((p) => p + 1)} className="rounded border px-2 py-1 disabled:opacity-40">Next</button>
        </div>
      </nav>

      {toast && (
        <div role="status" className="fixed bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-4 rounded-md bg-slate-900 px-4 py-2 text-sm text-white shadow-lg">
          <span>
            {toast.action === "archive" ? "Archived" : "Moved to trash"} {toast.affected.toLocaleString()} document{toast.affected === 1 ? "" : "s"}.
          </span>
          <button
            type="button"
            className="font-semibold text-blue-300 hover:text-blue-200"
            onClick={() => { bulk.undo(toast.batchId); setToast(null); }}
          >
            Undo
          </button>
        </div>
      )}
    </div>
  );
}
```

**Server contract this relies on** (`POST /api/documents/bulk`): honour `Idempotency-Key`; for `target.kind === "filter"`, run `COUNT(*)` under the filter inside the same transaction and return `409 {expected, actual}` if it differs from `expectedTotal`; record every affected id under `batchId` so `/undo` can reverse it. Archive and trash are both status flips, never hard deletes.

`★ Insight ─────────────────────────────────────`
- **Selection is a union, not a Set.** Thousands of rows can't live client-side as ids, so "all matching" ships the *filter* plus the count the user saw. The server's count check turns "I thought I selected 3,000 but 3,400 match now" from a silent over-reach into a 409 nothing-happened.
- **Undo beats confirm.** Both actions execute immediately and offer an 8s undo; only Trash above 200 items adds type-the-count. That friction sits exactly where the blast radius is, and nowhere else.
- **Idempotency key per arming, not per click.** A double-click, a retry after a timeout, or a flaky network all resolve to one mutation on the server (hazard M2 from two sides).
`─────────────────────────────────────────────────`

**What's left possible on purpose:** Archive never asks for confirmation at any size, because it's fully reversible — gating it would train click-through for the Trash gate. Selection clears on filter change rather than being preserved; carrying it across filters is precisely how people trash things they no longer see.