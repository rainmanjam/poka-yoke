Read the routing skill (`poka-yoke` → `ux`, since this is a UI build with a destructive bulk action) and its patterns reference. Building the component now, applying the ladder from that skill: undo-over-confirm for the reversible Archive, scale-aware type-to-confirm for the irreversible bulk Delete, and an explicit "N on this page" vs "all N,NNN matching" selection split so bulk scope is never invisible.

★ Insight ─────────────────────────────────────
Selecting "all" across a paginated list has a well-known trap: does it mean the 50 rows on screen, or every row matching the filter? I'm modeling selection as a discriminated union (`explicit` vs `allMatching`) instead of one `Set<string>` — this makes "selected all 3,482 but explicitly excluded 3 of them" a representable, cheap state instead of something you'd have to fake by enumerating thousands of IDs client-side.
─────────────────────────────────────────────────

## `types.ts`

```ts
export interface Document {
  id: string;
  title: string;
  updatedAt: string; // ISO 8601
  ownerName: string;
}

// Whatever the table's current search/sort/filter state is.
// Bulk mutations against "all matching" send this instead of an ID list.
export interface DocumentFilter {
  search?: string;
  ownerId?: string;
  sort?: string;
}

export type BulkPayload =
  | { ids: string[] }
  | { filter: DocumentFilter; excludeIds: string[] };
```

## `useBulkSelection.ts`

```ts
import { useMemo, useReducer } from "react";

export type Selection =
  | { kind: "explicit"; ids: Set<string> }
  | { kind: "allMatching"; excludedIds: Set<string> };

type Action =
  | { type: "toggleRow"; id: string }
  | { type: "toggleAllOnPage"; pageIds: string[] }
  | { type: "selectAllMatching" }
  | { type: "clear" };

function reducer(state: Selection, action: Action): Selection {
  switch (action.type) {
    case "toggleRow": {
      if (state.kind === "explicit") {
        const ids = new Set(state.ids);
        ids.has(action.id) ? ids.delete(action.id) : ids.add(action.id);
        return { kind: "explicit", ids };
      }
      const excludedIds = new Set(state.excludedIds);
      excludedIds.has(action.id) ? excludedIds.delete(action.id) : excludedIds.add(action.id);
      return { kind: "allMatching", excludedIds };
    }
    case "toggleAllOnPage": {
      if (state.kind === "explicit") {
        const allSelected = action.pageIds.every((id) => state.ids.has(id));
        const ids = new Set(state.ids);
        action.pageIds.forEach((id) => (allSelected ? ids.delete(id) : ids.add(id)));
        return { kind: "explicit", ids };
      }
      const allSelected = action.pageIds.every((id) => !state.excludedIds.has(id));
      const excludedIds = new Set(state.excludedIds);
      action.pageIds.forEach((id) => (allSelected ? excludedIds.add(id) : excludedIds.delete(id)));
      return { kind: "allMatching", excludedIds };
    }
    case "selectAllMatching":
      return { kind: "allMatching", excludedIds: new Set() };
    case "clear":
      return { kind: "explicit", ids: new Set() };
  }
}

export function useBulkSelection(totalCount: number) {
  const [selection, dispatch] = useReducer(reducer, { kind: "explicit", ids: new Set<string>() });

  const selectedCount = selection.kind === "explicit" ? selection.ids.size : totalCount - selection.excludedIds.size;

  const isSelected = (id: string) =>
    selection.kind === "explicit" ? selection.ids.has(id) : !selection.excludedIds.has(id);

  const toPayload = (filter: DocumentFilterLike): BulkPayload =>
    selection.kind === "explicit"
      ? { ids: Array.from(selection.ids) }
      : { filter, excludeIds: Array.from(selection.excludedIds) };

  return useMemo(
    () => ({
      selection,
      selectedCount,
      isSelected,
      toggleRow: (id: string) => dispatch({ type: "toggleRow", id }),
      toggleAllOnPage: (pageIds: string[]) => dispatch({ type: "toggleAllOnPage", pageIds }),
      selectAllMatching: () => dispatch({ type: "selectAllMatching" }),
      clear: () => dispatch({ type: "clear" }),
      toPayload,
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selection, totalCount]
  );
}

// local alias to avoid importing the app-wide type name twice above
type DocumentFilterLike = { search?: string; ownerId?: string; sort?: string };
```

## `api/documents.ts`

```ts
import type { BulkPayload } from "../types";

async function postBulk<T>(url: string, payload: BulkPayload, idempotencyKey: string): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey, // survives retry on refresh/network flake — same op, not a new one
    },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Request failed (${res.status})`);
  }
  return res.json();
}

export const archiveDocuments = (payload: BulkPayload, idempotencyKey: string) =>
  postBulk<{ archivedCount: number }>("/api/documents/bulk-archive", payload, idempotencyKey);

export const unarchiveDocuments = (payload: BulkPayload, idempotencyKey: string) =>
  postBulk<{ unarchivedCount: number }>("/api/documents/bulk-unarchive", payload, idempotencyKey);

export const deleteDocuments = (payload: BulkPayload, idempotencyKey: string) =>
  postBulk<{ deletedCount: number }>("/api/documents/bulk-delete", payload, idempotencyKey);
```

## `BulkActionsBar.tsx`

```tsx
import { useRef, useState } from "react";
import type { BulkPayload, DocumentFilter } from "./types";
import { archiveDocuments, deleteDocuments, unarchiveDocuments } from "./api/documents";

interface BulkActionsBarProps {
  selectedCount: number;
  payload: BulkPayload;
  filter: DocumentFilter;
  onSettled: () => void; // parent refetches the current page / clears selection
}

export function BulkActionsBar({ selectedCount, payload, onSettled }: BulkActionsBarProps) {
  const [pending, setPending] = useState<"archive" | "delete" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [undoToast, setUndoToast] = useState<{ message: string; onUndo: () => void } | null>(null);

  if (selectedCount === 0) return null;

  async function handleArchive() {
    if (pending) return; // structural double-submit guard, not just a visual one
    setPending("archive");
    setError(null);
    const key = crypto.randomUUID();
    try {
      const { archivedCount } = await archiveDocuments(payload, key);
      setUndoToast({
        message: `Archived ${archivedCount.toLocaleString()} document${archivedCount === 1 ? "" : "s"}.`,
        onUndo: async () => {
          setUndoToast(null);
          await unarchiveDocuments(payload, crypto.randomUUID());
          onSettled();
        },
      });
      onSettled();
    } catch {
      setError("Couldn't archive those documents. Nothing was changed — try again.");
    } finally {
      setPending(null);
    }
  }

  async function handleConfirmDelete() {
    setPending("delete");
    setError(null);
    try {
      await deleteDocuments(payload, crypto.randomUUID());
      setConfirmingDelete(false);
      onSettled();
    } catch {
      setError("Couldn't delete those documents. Nothing was changed — try again.");
    } finally {
      setPending(null);
    }
  }

  return (
    <>
      <div className="sticky bottom-0 flex items-center justify-between border-t border-gray-200 bg-white px-4 py-3 shadow-[0_-1px_4px_rgba(0,0,0,0.06)]">
        <span className="text-sm font-medium text-gray-900">
          {selectedCount.toLocaleString()} selected
        </span>
        <div className="flex items-center gap-2">
          {error && <span className="text-sm text-red-600">{error}</span>}
          <button
            onClick={handleArchive}
            disabled={pending !== null}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {pending === "archive" ? "Archiving…" : "Archive"}
          </button>
          {/* Destructive action: separated spatially and styled distinctly from Archive, per the
              "never give a destructive action the same weight as a benign one" pattern. */}
          <button
            onClick={() => setConfirmingDelete(true)}
            disabled={pending !== null}
            className="rounded border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            Delete
          </button>
        </div>
      </div>

      {confirmingDelete && (
        <ConfirmBulkDeleteDialog
          count={selectedCount}
          pending={pending === "delete"}
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={handleConfirmDelete}
        />
      )}

      {undoToast && (
        <div className="fixed bottom-4 left-1/2 flex -translate-x-1/2 items-center gap-3 rounded-lg bg-gray-900 px-4 py-2.5 text-sm text-white shadow-lg">
          <span>{undoToast.message}</span>
          <button
            onClick={undoToast.onUndo}
            className="font-semibold text-blue-300 hover:text-blue-200"
          >
            Undo
          </button>
        </div>
      )}
    </>
  );
}

function ConfirmBulkDeleteDialog({
  count,
  pending,
  onConfirm,
  onCancel,
}: {
  count: number;
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const [typed, setTyped] = useState("");
  const confirmTarget = String(count);
  const canConfirm = typed.trim() === confirmTarget && !pending;

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="bulk-delete-title" className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 id="bulk-delete-title" className="text-lg font-semibold text-gray-900">
          Delete {count.toLocaleString()} document{count === 1 ? "" : "s"}?
        </h2>
        <p className="mt-2 text-sm text-gray-600">
          This permanently deletes {count.toLocaleString()} document{count === 1 ? "" : "s"}. This
          can&apos;t be undone. Type <span className="font-mono font-semibold">{confirmTarget}</span> to confirm.
        </p>
        <input
          autoFocus
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
          placeholder={confirmTarget}
          inputMode="numeric"
          className="mt-3 w-full rounded border border-gray-300 px-3 py-2 text-sm focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500"
        />
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onCancel} className="rounded px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100">
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!canConfirm}
            className="rounded bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-red-300"
          >
            {pending ? "Deleting…" : "Delete forever"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

## `DocumentsTable.tsx`

```tsx
import { useEffect, useRef } from "react";
import type { Document, DocumentFilter } from "./types";
import { useBulkSelection } from "./useBulkSelection";
import { BulkActionsBar } from "./BulkActionsBar";

interface DocumentsTableProps {
  documents: Document[]; // current page, up to 50 rows
  totalCount: number; // total matching the current filter, can be in the thousands
  filter: DocumentFilter;
  onRefetch: () => void;
}

export function DocumentsTable({ documents, totalCount, filter, onRefetch }: DocumentsTableProps) {
  const { selection, selectedCount, isSelected, toggleRow, toggleAllOnPage, selectAllMatching, clear, toPayload } =
    useBulkSelection(totalCount);

  const pageIds = documents.map((d) => d.id);
  const allOnPageSelected = pageIds.length > 0 && pageIds.every(isSelected);
  const someOnPageSelected = !allOnPageSelected && pageIds.some(isSelected);

  const headerCheckboxRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (headerCheckboxRef.current) headerCheckboxRef.current.indeterminate = someOnPageSelected;
  }, [someOnPageSelected]);

  // Only offer "select all matching" once the visible page is fully selected —
  // otherwise the banner is a non-sequitur ("select all 3,482" when 12 of 50 are checked).
  const showSelectAllBanner = selection.kind === "explicit" && allOnPageSelected && totalCount > pageIds.length;

  return (
    <div>
      {showSelectAllBanner && (
        <div className="flex items-center justify-between bg-blue-50 px-4 py-2 text-sm text-blue-900">
          <span>All {pageIds.length} documents on this page are selected.</span>
          <button className="font-medium underline" onClick={selectAllMatching}>
            Select all {totalCount.toLocaleString()} matching documents
          </button>
        </div>
      )}
      {selection.kind === "allMatching" && (
        <div className="flex items-center justify-between bg-blue-50 px-4 py-2 text-sm text-blue-900">
          <span>
            All {totalCount.toLocaleString()} matching documents selected
            {selection.excludedIds.size > 0 && ` (${selection.excludedIds.size} deselected)`}.
          </span>
          <button className="font-medium underline" onClick={clear}>
            Clear selection
          </button>
        </div>
      )}

      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-gray-200">
            <th className="w-10 px-4 py-2">
              <input
                ref={headerCheckboxRef}
                type="checkbox"
                checked={allOnPageSelected}
                onChange={() => toggleAllOnPage(pageIds)}
                aria-label="Select all documents on this page"
              />
            </th>
            <th className="px-4 py-2 font-medium text-gray-600">Title</th>
            <th className="px-4 py-2 font-medium text-gray-600">Owner</th>
            <th className="px-4 py-2 font-medium text-gray-600">Updated</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id} className="border-b border-gray-100 hover:bg-gray-50">
              <td className="px-4 py-2">
                <input
                  type="checkbox"
                  checked={isSelected(doc.id)}
                  onChange={() => toggleRow(doc.id)}
                  aria-label={`Select ${doc.title}`}
                />
              </td>
              <td className="px-4 py-2 text-gray-900">{doc.title}</td>
              <td className="px-4 py-2 text-gray-600">{doc.ownerName}</td>
              <td className="px-4 py-2 text-gray-600">{new Date(doc.updatedAt).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <BulkActionsBar
        selectedCount={selectedCount}
        payload={toPayload(filter)}
        filter={filter}
        onSettled={() => {
          clear();
          onRefetch();
        }}
      />
    </div>
  );
}
```

★ Insight ─────────────────────────────────────
`onSettled` clears selection and asks the parent to refetch, rather than the bar mutating the `documents` array itself. That keeps the bar ignorant of how the table gets its data (REST, GraphQL, cache) — it only knows "an action finished, go get fresh state" — which also sidesteps a subtle bug: if it tried to splice archived IDs out of a local array, an `allMatching` selection wouldn't know which of the thousands of off-page rows to remove.
─────────────────────────────────────────────────

Closing note, per the ux skill's convention:

- **Control-rung**: the mutate buttons are structurally disabled while a request is in flight (`pending !== null`), so double-click/refresh-triggered retries can't fire a second bulk op — paired with an idempotency key in case the network retries anyway.
- **Control-rung**: "select all on page" vs "select all N matching" are different selection states, not the same button meaning different things depending on a flag no one can see — you cannot accidentally select 3,482 documents by clicking a header checkbox meant for 50.
- **Warning-rung** on purpose for Delete: I required typing the exact count rather than a fixed word like "DELETE", because for a bulk action the number *is* the fact most likely to be wrong (e.g. a stale `allMatching` selection after a filter change) — reproducing it forces the user to actually read it. I didn't make delete reversible (soft-delete + trash) even though that's the stronger Control-rung device in the pattern reference, because that's a backend/schema decision outside a UI component — flagging it as the better fix if the API can support it.
- **Left possible on purpose**: Archive commits immediately rather than delaying commit for the undo window (Gmail-style), since archive is cheap to reverse server-side and immediate commit is simpler and correct for a multi-viewer document list.