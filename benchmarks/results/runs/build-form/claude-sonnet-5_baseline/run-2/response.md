I'll build this directly per your instructions — no clarifying questions, reasonable assumptions called out inline. Key assumption: data fetching (React Query/SWR/whatever) lives in the parent; this component receives the current page of documents + `totalCount` as props and calls `onRefetch` after a mutation, since that's where pagination logic already lives in most codebases.

Given the "thousands of matching documents" detail, the interesting design problem is the Gmail-style **"select all 50 on this page" → "select all 3,482 matching"** escalation, since you can't hold thousands of checkbox states or send thousands of IDs to a delete endpoint.

```ts
// types.ts
export interface Document {
  id: string;
  title: string;
  updatedAt: string; // ISO string
  ownerName: string;
}

export interface DocumentFilter {
  query?: string;
  ownerId?: string;
  // ...whatever else drives the current list view
}

export type BulkSelectionPayload =
  | { ids: string[] }
  | { filter: DocumentFilter; excludeIds: string[] };
```

```ts
// api/documents.ts
import type { BulkSelectionPayload } from "../types";

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const message = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${message}`);
  }

  return res.json() as Promise<T>;
}

export function bulkArchiveDocuments(payload: BulkSelectionPayload) {
  return postJson<{ affected: number }>("/api/documents/bulk-archive", payload);
}

export function bulkDeleteDocuments(payload: BulkSelectionPayload) {
  return postJson<{ affected: number }>("/api/documents/bulk-delete", payload);
}
```

★ Insight ─────────────────────────────────────
The mutation payload is a discriminated union (`{ids}` vs `{filter, excludeIds}`), not `{ids, filter?, excludeIds?}`. If a "select all matching" bulk-delete ever sent both `ids` and `filter`, the backend has to decide which one wins — that's a footgun that a union at the type level makes unrepresentable instead of something you'd catch in code review.
─────────────────────────────────────────────────

```ts
// hooks/useSelection.ts
import { useMemo, useState, useCallback } from "react";
import type { BulkSelectionPayload, DocumentFilter } from "../types";

interface SelectionState {
  selectedIds: Set<string>;
  excludedIds: Set<string>;
  isAllMatchingSelected: boolean;
}

const EMPTY: SelectionState = {
  selectedIds: new Set(),
  excludedIds: new Set(),
  isAllMatchingSelected: false,
};

export function useSelection(totalCount: number) {
  const [state, setState] = useState<SelectionState>(EMPTY);

  const selectedCount = state.isAllMatchingSelected
    ? totalCount - state.excludedIds.size
    : state.selectedIds.size;

  const isRowSelected = useCallback(
    (id: string) =>
      state.isAllMatchingSelected
        ? !state.excludedIds.has(id)
        : state.selectedIds.has(id),
    [state]
  );

  const toggleRow = useCallback((id: string, checked: boolean) => {
    setState((prev) => {
      if (prev.isAllMatchingSelected) {
        const excludedIds = new Set(prev.excludedIds);
        checked ? excludedIds.delete(id) : excludedIds.add(id);
        return { ...prev, excludedIds };
      }
      const selectedIds = new Set(prev.selectedIds);
      checked ? selectedIds.add(id) : selectedIds.delete(id);
      return { ...prev, selectedIds };
    });
  }, []);

  const toggleAllOnPage = useCallback((pageIds: string[], checked: boolean) => {
    setState((prev) => {
      if (prev.isAllMatchingSelected) {
        const excludedIds = new Set(prev.excludedIds);
        pageIds.forEach((id) => (checked ? excludedIds.delete(id) : excludedIds.add(id)));
        return { ...prev, excludedIds };
      }
      const selectedIds = new Set(prev.selectedIds);
      pageIds.forEach((id) => (checked ? selectedIds.add(id) : selectedIds.delete(id)));
      return { ...prev, selectedIds };
    });
  }, []);

  const selectAllMatching = useCallback(() => {
    setState({ selectedIds: new Set(), excludedIds: new Set(), isAllMatchingSelected: true });
  }, []);

  const clear = useCallback(() => setState(EMPTY), []);

  const toPayload = useCallback(
    (filter: DocumentFilter): BulkSelectionPayload =>
      state.isAllMatchingSelected
        ? { filter, excludeIds: Array.from(state.excludedIds) }
        : { ids: Array.from(state.selectedIds) },
    [state]
  );

  // Was every id on the current page selected? Drives the header checkbox's checked/indeterminate state.
  const pageSelectionStatus = useCallback(
    (pageIds: string[]): "none" | "some" | "all" => {
      const selected = pageIds.filter(isRowSelected).length;
      if (selected === 0) return "none";
      if (selected === pageIds.length) return "all";
      return "some";
    },
    [isRowSelected]
  );

  return useMemo(
    () => ({
      selectedCount,
      isRowSelected,
      toggleRow,
      toggleAllOnPage,
      selectAllMatching,
      clear,
      toPayload,
      pageSelectionStatus,
      isAllMatchingSelected: state.isAllMatchingSelected,
    }),
    [selectedCount, isRowSelected, toggleRow, toggleAllOnPage, selectAllMatching, clear, toPayload, pageSelectionStatus, state.isAllMatchingSelected]
  );
}
```

```tsx
// components/ConfirmDialog.tsx
interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  isBusy?: boolean;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  onConfirm,
  onCancel,
  isBusy,
}: ConfirmDialogProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
    >
      <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl">
        <h2 id="confirm-dialog-title" className="text-base font-semibold text-gray-900">
          {title}
        </h2>
        <p className="mt-2 text-sm text-gray-600">{description}</p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={isBusy}
            className="rounded-md px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isBusy}
            className="rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            {isBusy ? "Deleting…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
```

```tsx
// components/BulkActionsBar.tsx
interface BulkActionsBarProps {
  selectedCount: number;
  totalCount: number;
  isAllMatchingSelected: boolean;
  showSelectAllPrompt: boolean; // true when every row on the page is checked but not all matching
  onSelectAllMatching: () => void;
  onClear: () => void;
  onArchive: () => void;
  onDelete: () => void;
  isArchiving: boolean;
  isDeleting: boolean;
}

export function BulkActionsBar({
  selectedCount,
  totalCount,
  isAllMatchingSelected,
  showSelectAllPrompt,
  onSelectAllMatching,
  onClear,
  onArchive,
  onDelete,
  isArchiving,
  isDeleting,
}: BulkActionsBarProps) {
  if (selectedCount === 0) return null;

  const isBusy = isArchiving || isDeleting;

  return (
    <div className="sticky top-0 z-10 flex flex-col gap-2 border-b border-blue-100 bg-blue-50 px-4 py-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-sm text-blue-900">
          <span className="font-medium">
            {selectedCount.toLocaleString()} selected
          </span>
          <button
            type="button"
            onClick={onClear}
            className="text-blue-700 underline-offset-2 hover:underline"
          >
            Clear
          </button>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onArchive}
            disabled={isBusy}
            className="rounded-md border border-blue-300 bg-white px-3 py-1.5 text-sm font-medium text-blue-900 hover:bg-blue-100 disabled:opacity-50"
          >
            {isArchiving ? "Archiving…" : "Archive"}
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={isBusy}
            className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            Delete
          </button>
        </div>
      </div>

      {showSelectAllPrompt && !isAllMatchingSelected && (
        <p className="text-sm text-blue-800">
          All {selectedCount} documents on this page are selected.{" "}
          <button type="button" onClick={onSelectAllMatching} className="font-medium underline">
            Select all {totalCount.toLocaleString()} matching documents
          </button>
        </p>
      )}
    </div>
  );
}
```

```tsx
// components/DocumentsTable.tsx
import { useRef, useEffect, useState } from "react";
import type { Document, DocumentFilter } from "../types";
import { useSelection } from "../hooks/useSelection";
import { bulkArchiveDocuments, bulkDeleteDocuments } from "../api/documents";
import { BulkActionsBar } from "./BulkActionsBar";
import { ConfirmDialog } from "./ConfirmDialog";

interface DocumentsTableProps {
  documents: Document[]; // current page, up to 50 rows
  totalCount: number; // total matching the current filter, can be in the thousands
  filter: DocumentFilter; // whatever filter/search state produced `documents`
  onRefetch: () => void; // re-run the current page's query after a mutation
  onMutationError: (message: string) => void; // surface errors via the caller's toast/banner system
}

function HeaderCheckbox({
  status,
  onChange,
}: {
  status: "none" | "some" | "all";
  onChange: (checked: boolean) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = status === "some";
  }, [status]);

  return (
    <input
      ref={ref}
      type="checkbox"
      checked={status === "all"}
      onChange={(e) => onChange(e.target.checked)}
      aria-label="Select all documents on this page"
      className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
    />
  );
}

export function DocumentsTable({
  documents,
  totalCount,
  filter,
  onRefetch,
  onMutationError,
}: DocumentsTableProps) {
  const selection = useSelection(totalCount);
  const [isArchiving, setIsArchiving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const pageIds = documents.map((d) => d.id);
  const pageStatus = selection.pageSelectionStatus(pageIds);

  async function handleArchive() {
    setIsArchiving(true);
    try {
      await bulkArchiveDocuments(selection.toPayload(filter));
      selection.clear();
      onRefetch();
    } catch (err) {
      onMutationError(err instanceof Error ? err.message : "Failed to archive documents.");
    } finally {
      setIsArchiving(false);
    }
  }

  async function handleDeleteConfirmed() {
    setIsDeleting(true);
    try {
      await bulkDeleteDocuments(selection.toPayload(filter));
      selection.clear();
      setConfirmingDelete(false);
      onRefetch();
    } catch (err) {
      onMutationError(err instanceof Error ? err.message : "Failed to delete documents.");
    } finally {
      setIsDeleting(false);
    }
  }

  return (
    <div className="flex flex-col">
      <BulkActionsBar
        selectedCount={selection.selectedCount}
        totalCount={totalCount}
        isAllMatchingSelected={selection.isAllMatchingSelected}
        showSelectAllPrompt={pageStatus === "all"}
        onSelectAllMatching={selection.selectAllMatching}
        onClear={selection.clear}
        onArchive={handleArchive}
        onDelete={() => setConfirmingDelete(true)}
        isArchiving={isArchiving}
        isDeleting={isDeleting}
      />

      <table className="min-w-full divide-y divide-gray-200">
        <thead className="bg-gray-50">
          <tr>
            <th className="w-10 px-4 py-3">
              <HeaderCheckbox
                status={pageStatus}
                onChange={(checked) => selection.toggleAllOnPage(pageIds, checked)}
              />
            </th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Title</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Owner</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Updated</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {documents.map((doc) => {
            const checked = selection.isRowSelected(doc.id);
            return (
              <tr key={doc.id} className={checked ? "bg-blue-50/50" : undefined}>
                <td className="w-10 px-4 py-3">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => selection.toggleRow(doc.id, e.target.checked)}
                    aria-label={`Select ${doc.title}`}
                    className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                </td>
                <td className="px-4 py-3 text-sm text-gray-900">{doc.title}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{doc.ownerName}</td>
                <td className="px-4 py-3 text-sm text-gray-600">
                  {new Date(doc.updatedAt).toLocaleDateString()}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <ConfirmDialog
        open={confirmingDelete}
        title={`Delete ${selection.selectedCount.toLocaleString()} document${selection.selectedCount === 1 ? "" : "s"}?`}
        description="This can't be undone. Documents will be permanently removed."
        confirmLabel="Delete"
        onConfirm={handleDeleteConfirmed}
        onCancel={() => setConfirmingDelete(false)}
        isBusy={isDeleting}
      />
    </div>
  );
}
```

★ Insight ─────────────────────────────────────
`toggleAllOnPage` and `toggleRow` branch on `isAllMatchingSelected` and flip to editing `excludedIds` instead of `selectedIds`. That's the piece that makes "select all 3,482, then uncheck 2 outliers, then bulk-archive the rest" actually work — without it, unchecking a row after "select all matching" would have nothing to remove from, since that row's id was never added to a selection set in the first place.
─────────────────────────────────────────────────

Two things I deliberately left as assumptions since they weren't specified: **Archive has no confirmation dialog** (I treated it as reversible/non-destructive, unlike Delete), and **there's no undo after delete** — if the backend actually soft-deletes with a trash/undo window, the bar should show an "Undo" toast instead of a hard confirm dialog, which is a UX call worth revisiting once you know the backend's actual delete semantics.