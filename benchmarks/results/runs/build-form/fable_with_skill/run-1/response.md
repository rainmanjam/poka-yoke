Read the router, the `ux` sub-skill, its pattern reference, and the M2 (non-idempotent retry) hazard. Since this is "building, not reviewing," the deliverable is the working component with a short closing note. Writing it now.

Assumptions I made: TypeScript, React 18, TanStack Query for mutations, a REST backend where delete is a soft-delete into a 30-day trash, and list filters are a plain object (`{ query, ownerId }`).

## `types.ts`

```ts
// Branded ID: a DocumentId cannot be confused with an owner ID or a raw string.
export type DocumentId = string & { readonly __brand: "DocumentId" };
export const asDocumentId = (s: string) => s as DocumentId;

export interface Document {
  id: DocumentId;
  title: string;
  updatedAt: string; // ISO
  ownerName: string;
}

export interface DocumentFilter {
  query?: string;
  ownerId?: string;
}

/**
 * Selection is a discriminated union so "the 50 rows I ticked" and
 * "every one of the 4,312 matching documents" are different shapes and
 * cannot be silently conflated by the bar or the API.
 */
export type Selection =
  | { mode: "none" }
  | { mode: "ids"; ids: ReadonlySet<DocumentId> }
  | {
      mode: "all-matching";
      filter: DocumentFilter;          // snapshot at the moment of selecting
      totalCount: number;              // snapshot; server re-verifies this
      excludedIds: ReadonlySet<DocumentId>;
    };

export type BulkVerb = "archive" | "delete";
```

## `selection.ts` — state handling

```ts
import { useReducer, useCallback, useEffect } from "react";
import type { Document, DocumentFilter, DocumentId, Selection } from "./types";

type Action =
  | { type: "toggle"; id: DocumentId }
  | { type: "togglePage"; pageIds: DocumentId[] }
  | { type: "selectAllMatching"; filter: DocumentFilter; totalCount: number }
  | { type: "clear" };

function reduce(state: Selection, a: Action): Selection {
  switch (a.type) {
    case "clear":
      return { mode: "none" };

    case "selectAllMatching":
      return { mode: "all-matching", filter: a.filter, totalCount: a.totalCount, excludedIds: new Set() };

    case "toggle": {
      if (state.mode === "all-matching") {
        const excludedIds = new Set(state.excludedIds);
        excludedIds.has(a.id) ? excludedIds.delete(a.id) : excludedIds.add(a.id);
        return { ...state, excludedIds };
      }
      const ids = new Set(state.mode === "ids" ? state.ids : []);
      ids.has(a.id) ? ids.delete(a.id) : ids.add(a.id);
      return ids.size === 0 ? { mode: "none" } : { mode: "ids", ids };
    }

    case "togglePage": {
      // Header checkbox only ever means "this page". Never "all matching" — that is a
      // separate, explicit action with the count in its label.
      if (state.mode === "all-matching") return state;
      const ids = new Set(state.mode === "ids" ? state.ids : []);
      const allOnPageSelected = a.pageIds.every((id) => ids.has(id));
      a.pageIds.forEach((id) => (allOnPageSelected ? ids.delete(id) : ids.add(id)));
      return ids.size === 0 ? { mode: "none" } : { mode: "ids", ids };
    }
  }
}

export function selectedCount(s: Selection): number {
  if (s.mode === "none") return 0;
  if (s.mode === "ids") return s.ids.size;
  return s.totalCount - s.excludedIds.size;
}

export function isSelected(s: Selection, id: DocumentId): boolean {
  if (s.mode === "none") return false;
  if (s.mode === "ids") return s.ids.has(id);
  return !s.excludedIds.has(id);
}

export function useSelection(filter: DocumentFilter) {
  const [selection, dispatch] = useReducer(reduce, { mode: "none" });

  // A selection made under one filter must not survive into another —
  // the rows the user thinks they picked are no longer the rows on screen.
  const filterKey = JSON.stringify(filter);
  useEffect(() => { dispatch({ type: "clear" }); }, [filterKey]);

  return {
    selection,
    toggle: useCallback((id: DocumentId) => dispatch({ type: "toggle", id }), []),
    togglePage: useCallback((docs: Document[]) => dispatch({ type: "togglePage", pageIds: docs.map((d) => d.id) }), []),
    selectAllMatching: useCallback((totalCount: number) => dispatch({ type: "selectAllMatching", filter, totalCount }), [filterKey]),
    clear: useCallback(() => dispatch({ type: "clear" }), []),
  };
}
```

## `api.ts` — mutation calls

```ts
import type { BulkVerb, DocumentFilter, DocumentId, Selection } from "./types";

/** Wire shape mirrors the Selection union: the server cannot receive an ambiguous "all". */
export type BulkTarget =
  | { kind: "ids"; ids: DocumentId[] }
  | { kind: "filter"; filter: DocumentFilter; excludeIds: DocumentId[]; expectedCount: number };

export function toTarget(s: Selection): BulkTarget {
  switch (s.mode) {
    case "none": throw new Error("No selection"); // unreachable: bar is not rendered when none
    case "ids": return { kind: "ids", ids: [...s.ids] };
    case "all-matching":
      return { kind: "filter", filter: s.filter, excludeIds: [...s.excludedIds], expectedCount: s.totalCount - s.excludedIds.size };
  }
}

export interface BulkResult { affected: number; batchId: string }

/**
 * idempotencyKey is REQUIRED, not optional. Refresh, double-click, or a retried
 * request with the same key is a no-op server-side.
 * expectedCount on filter targets lets the server refuse with 409 if the matching
 * set changed since the user saw the number.
 */
export async function bulkMutate(verb: BulkVerb, target: BulkTarget, idempotencyKey: string): Promise<BulkResult> {
  const res = await fetch(`/api/documents/bulk/${verb}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(target),
  });
  if (res.status === 409) throw new CountDriftError();
  if (!res.ok) throw new Error(`${verb} failed: ${res.status}`);
  return res.json();
}

/** Every bulk op returns a batchId; undo is one call, not N. */
export async function undoBatch(batchId: string): Promise<void> {
  const res = await fetch(`/api/documents/bulk/undo/${batchId}`, { method: "POST" });
  if (!res.ok) throw new Error(`undo failed: ${res.status}`);
}

export class CountDriftError extends Error {
  constructor() { super("The set of matching documents changed. Review the selection and try again."); }
}
```

## `useBulkAction.ts` — commit with grace-period undo

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { bulkMutate, toTarget, undoBatch, type BulkResult } from "./api";
import type { BulkVerb, Selection } from "./types";

const UNDO_WINDOW_MS = 8000;

export type Toast = { verb: BulkVerb; affected: number; batchId: string; undone: boolean } | null;

export function useBulkAction(onSettled: () => void) {
  const qc = useQueryClient();
  const [toast, setToast] = useState<Toast>(null);
  const timer = useRef<number>();

  const mutation = useMutation({
    mutationFn: ({ verb, selection }: { verb: BulkVerb; selection: Selection }) =>
      // Key is minted here, once per click. A retry inside fetch reuses it.
      bulkMutate(verb, toTarget(selection), crypto.randomUUID()),
    onSuccess: (r: BulkResult, { verb }) => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      setToast({ verb, affected: r.affected, batchId: r.batchId, undone: false });
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setToast(null), UNDO_WINDOW_MS);
    },
    onSettled,
  });

  const undo = async () => {
    if (!toast || toast.undone) return;
    await undoBatch(toast.batchId);
    qc.invalidateQueries({ queryKey: ["documents"] });
    setToast({ ...toast, undone: true });
    timer.current = window.setTimeout(() => setToast(null), 2500);
  };

  return { run: mutation.mutate, isPending: mutation.isPending, error: mutation.error, toast, undo };
}
```

## `BulkActionsBar.tsx`

```tsx
import { useState } from "react";
import { selectedCount } from "./selection";
import type { BulkVerb, Selection } from "./types";

// Above this, Delete requires the user to reproduce the count — they cannot
// click through a number they never read.
const TYPE_TO_CONFIRM_THRESHOLD = 50;

interface Props {
  selection: Selection;
  pageSize: number;
  totalMatching: number;
  isPending: boolean;
  error: Error | null;
  onSelectAllMatching: () => void;
  onClear: () => void;
  onRun: (verb: BulkVerb) => void;
}

export function BulkActionsBar(p: Props) {
  const count = selectedCount(p.selection);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [typed, setTyped] = useState("");

  if (p.selection.mode === "none") return null; // bar does not exist without a selection

  const allMatching = p.selection.mode === "all-matching";
  const wholePageSelected = !allMatching && count === p.pageSize && p.totalMatching > p.pageSize;
  const needsTyped = count > TYPE_TO_CONFIRM_THRESHOLD;
  const typedMatches = typed.trim() === String(count);
  const scope = allMatching ? `all ${count.toLocaleString()} matching documents` : `${count} selected document${count === 1 ? "" : "s"}`;

  const runDelete = () => {
    setConfirmingDelete(false);
    setTyped("");
    p.onRun("delete");
  };

  return (
    <div role="region" aria-label="Bulk actions" aria-live="polite"
         className="sticky top-0 z-10 flex flex-wrap items-center gap-3 rounded-md border border-slate-300 bg-slate-50 px-4 py-2 text-sm">
      {/* Scale, always visible, always first. */}
      <span className="font-medium tabular-nums">{scope}</span>

      {wholePageSelected && (
        <button type="button" onClick={p.onSelectAllMatching} className="text-blue-700 underline">
          Select all {p.totalMatching.toLocaleString()} matching
        </button>
      )}
      <button type="button" onClick={p.onClear} className="text-slate-600 underline">Clear</button>

      {/* Archive: recoverable, so it is the primary-weight action with undo, no dialog. */}
      <button type="button" disabled={p.isPending} onClick={() => p.onRun("archive")}
              className="ml-auto rounded bg-slate-800 px-3 py-1.5 text-white disabled:opacity-50">
        {p.isPending ? "Working…" : `Archive ${count.toLocaleString()}`}
      </button>

      {/* Delete: spatially separated, outline style, never primary. */}
      <span className="mx-2 h-5 w-px bg-slate-300" aria-hidden />
      {!confirmingDelete ? (
        <button type="button" disabled={p.isPending} onClick={() => setConfirmingDelete(true)}
                className="rounded border border-red-600 px-3 py-1.5 text-red-700 disabled:opacity-50">
          Delete…
        </button>
      ) : (
        <div className="flex w-full items-center gap-2 border-t border-slate-200 pt-2 mt-1">
          <span>
            Move <strong>{scope}</strong> to trash? They can be restored for 30 days.
          </span>
          {needsTyped && (
            <label className="flex items-center gap-1">
              Type <code className="rounded bg-slate-200 px-1">{count}</code> to confirm
              <input autoFocus inputMode="numeric" value={typed} onChange={(e) => setTyped(e.target.value)}
                     className="w-20 rounded border px-1 py-0.5" aria-label={`Type ${count} to confirm`} />
            </label>
          )}
          <button type="button" onClick={() => { setConfirmingDelete(false); setTyped(""); }}
                  className="ml-auto rounded px-3 py-1.5 underline">Cancel</button>
          <button type="button"
                  aria-disabled={needsTyped && !typedMatches}
                  onClick={() => { if (!needsTyped || typedMatches) runDelete(); }}
                  className="rounded bg-red-700 px-3 py-1.5 text-white aria-disabled:opacity-40">
            Move {count.toLocaleString()} to trash
          </button>
        </div>
      )}

      {p.error && <p role="alert" className="w-full text-red-700">{p.error.message}</p>}
    </div>
  );
}
```

## `DocumentsTable.tsx` — wiring

```tsx
import { useQuery } from "@tanstack/react-query";
import { BulkActionsBar } from "./BulkActionsBar";
import { isSelected, useSelection } from "./selection";
import { useBulkAction } from "./useBulkAction";
import type { Document, DocumentFilter } from "./types";

const PAGE_SIZE = 50;

async function fetchPage(filter: DocumentFilter, page: number): Promise<{ items: Document[]; total: number }> {
  const q = new URLSearchParams({ ...(filter as Record<string, string>), page: String(page), size: String(PAGE_SIZE) });
  const r = await fetch(`/api/documents?${q}`);
  if (!r.ok) throw new Error("Failed to load documents");
  return r.json();
}

export function DocumentsTable({ filter, page }: { filter: DocumentFilter; page: number }) {
  const { data } = useQuery({ queryKey: ["documents", filter, page], queryFn: () => fetchPage(filter, page), placeholderData: (d) => d });
  const sel = useSelection(filter);
  const bulk = useBulkAction(sel.clear);
  const rows = data?.items ?? [];
  const pageAllSelected = rows.length > 0 && rows.every((d) => isSelected(sel.selection, d.id));

  return (
    <div className="space-y-2">
      <BulkActionsBar
        selection={sel.selection}
        pageSize={rows.length}
        totalMatching={data?.total ?? 0}
        isPending={bulk.isPending}
        error={bulk.error}
        onSelectAllMatching={() => sel.selectAllMatching(data?.total ?? 0)}
        onClear={sel.clear}
        onRun={(verb) => bulk.run({ verb, selection: sel.selection })}
      />

      {bulk.toast && (
        <div role="status" className="flex items-center gap-3 rounded bg-slate-900 px-4 py-2 text-sm text-white">
          {bulk.toast.undone
            ? `Restored ${bulk.toast.affected.toLocaleString()} documents.`
            : `${bulk.toast.verb === "archive" ? "Archived" : "Moved to trash"}: ${bulk.toast.affected.toLocaleString()} documents.`}
          {!bulk.toast.undone && (
            <button type="button" onClick={bulk.undo} className="ml-auto font-semibold underline">Undo</button>
          )}
        </div>
      )}

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left">
            <th className="w-8 p-2">
              <input type="checkbox" aria-label="Select all on this page"
                     checked={pageAllSelected}
                     disabled={sel.selection.mode === "all-matching"}
                     onChange={() => sel.togglePage(rows)} />
            </th>
            <th className="p-2">Title</th><th className="p-2">Owner</th><th className="p-2">Updated</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.id} className={isSelected(sel.selection, d.id) ? "bg-blue-50" : ""}>
              <td className="p-2">
                <input type="checkbox" aria-label={`Select ${d.title}`}
                       checked={isSelected(sel.selection, d.id)} onChange={() => sel.toggle(d.id)} />
              </td>
              <td className="p-2">{d.title}</td>
              <td className="p-2">{d.ownerName}</td>
              <td className="p-2">{new Date(d.updatedAt).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

`★ Insight ─────────────────────────────────────`
- The `Selection` union is the load-bearing device. "50 ticked rows" and "all 4,312 matching" are different *types*, and `toTarget` turns them into different *wire shapes* — so neither the bar nor the server can mistake one for the other.
- `expectedCount` on filter targets is a fixed-value check moved to the source: the server compares it to the live count and 409s if documents arrived/left between the user reading the number and clicking.
`─────────────────────────────────────────────────`

## Closing note

**Made impossible (Control):** acting on an ambiguous "all" — header checkbox is page-only; "all matching" is a separate button labelled with the count. Double submission — `isPending` disables the buttons *and* every request carries a required idempotency key. Acting on a stale selection — it's cleared whenever the filter changes, and `expectedCount` lets the server refuse drift. Mis-clicking Delete — it's visually separated, outline-styled, and the trash is restorable for 30 days, with one-call `undo` via `batchId`.

**Warning rung:** the inline delete confirmation names scope and count; above 50 items the user must type the count. Archive gets no dialog at all — it is reversible and the Undo toast covers it.

**Left possible on purpose:** archiving thousands with one click. It's fully recoverable, and gating reversible actions is how users learn to click through the gates that matter.

**Server side still needed** (not in scope, but the UI is only half the device): the idempotency key must be unique-constrained per `(user, key)` and reserved in the same transaction as the write; the filter target must be tenant-scoped server-side, not trusted from the client.