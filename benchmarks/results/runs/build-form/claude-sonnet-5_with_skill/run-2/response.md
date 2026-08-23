Using the `ux` poka-yoke skill (destructive bulk action in a table). Two hazards in the prompt itself shaped the design: "total can be in the thousands" means naive select-all would silently apply to unseen rows, and Delete is irreversible while Archive isn't — so they need different devices, not one generic confirm dialog.

★ Insight ─────────────────────────────────────
- "Select all" across a paginated list is a classic trap: a user checks the header box expecting "these 50" but a naive implementation means "all 3,482 matching." Gmail solves this with an explicit second click ("Select all N matching") plus an exclude-list for anything unchecked afterward — that's the `BulkSelection` union below, not just a boolean.
- Archive and Delete get different devices because they have different consequences, not because delete is bigger: Archive is server-reversible, so it gets immediate-fire + a reverse mutation on Undo. Delete has no reverse mutation, so it gets delayed-commit — the mutation genuinely doesn't fire until the grace window elapses, making "Undo" a guaranteed no-op cancel rather than a hope that un-deleting works.
─────────────────────────────────────────────────

```tsx
// types.ts
export interface Document {
  id: string;
  title: string;
  updatedAt: string; // ISO 8601
  ownerName: string;
}

export interface DocumentFilters {
  search: string;
  sortBy: 'updatedAt' | 'title' | 'ownerName';
  sortDir: 'asc' | 'desc';
}

// The two ways a bulk action can be scoped. A discriminated union instead of
// `{ ids: string[]; allMatching: boolean; excludedIds: string[] }` makes the
// mismatched case (allMatching: false but excludedIds populated) unrepresentable —
// contact-lens poka-yoke on the payload itself.
export type BulkSelection =
  | { mode: 'ids'; ids: string[] }
  | { mode: 'allMatching'; filters: DocumentFilters; excludedIds: string[] };
```

```tsx
// api/documents.ts
import type { BulkSelection } from './types';

async function postJson(url: string, body: unknown) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${url} failed: ${res.status}`);
  return res.json();
}

export const archiveDocuments = (selection: BulkSelection) =>
  postJson('/api/documents/bulk-archive', { selection });

export const unarchiveDocuments = (selection: BulkSelection) =>
  postJson('/api/documents/bulk-unarchive', { selection });

export const deleteDocuments = (selection: BulkSelection) =>
  postJson('/api/documents/bulk-delete', { selection });
```

```tsx
// hooks/useBulkSelection.ts
import { useCallback, useMemo, useState } from 'react';
import type { BulkSelection, DocumentFilters } from '../types';

interface UseBulkSelectionArgs {
  pageIds: string[];      // ids of rows on the currently rendered page
  totalMatching: number;  // total documents matching the current filters, across all pages
  filters: DocumentFilters;
}

export function useBulkSelection({ pageIds, totalMatching, filters }: UseBulkSelectionArgs) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectAllMatching, setSelectAllMatching] = useState(false);
  const [excludedIds, setExcludedIds] = useState<Set<string>>(new Set());

  const reset = useCallback(() => {
    setSelectedIds(new Set());
    setSelectAllMatching(false);
    setExcludedIds(new Set());
  }, []);

  const toggleRow = useCallback((id: string) => {
    if (selectAllMatching) {
      setExcludedIds(prev => {
        const next = new Set(prev);
        next.has(id) ? next.delete(id) : next.add(id);
        return next;
      });
      return;
    }
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, [selectAllMatching]);

  const isRowSelected = useCallback(
    (id: string) => (selectAllMatching ? !excludedIds.has(id) : selectedIds.has(id)),
    [selectAllMatching, excludedIds, selectedIds]
  );

  // Header checkbox reflects only the *current page* — never claims more than what's visible.
  const allOnPageSelected = pageIds.length > 0 && pageIds.every(isRowSelected);
  const someOnPageSelected = pageIds.some(isRowSelected) && !allOnPageSelected;

  const toggleAllOnPage = useCallback(() => {
    if (selectAllMatching) {
      // Deselecting the page while in "all matching" mode = exclude those ids.
      setExcludedIds(prev => {
        const next = new Set(prev);
        if (allOnPageSelected) pageIds.forEach(id => next.add(id));
        else pageIds.forEach(id => next.delete(id));
        return next;
      });
      return;
    }
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (allOnPageSelected) pageIds.forEach(id => next.delete(id));
      else pageIds.forEach(id => next.add(id));
      return next;
    });
  }, [allOnPageSelected, pageIds, selectAllMatching]);

  const selectAllMatchingFiltered = useCallback(() => {
    setSelectAllMatching(true);
    setExcludedIds(new Set());
    setSelectedIds(new Set());
  }, []);

  const selectedCount = selectAllMatching
    ? totalMatching - excludedIds.size
    : selectedIds.size;

  // Show the "select all N matching" banner only when the page is fully selected
  // AND there's more beyond this page to offer — otherwise it's a no-op prompt.
  const showSelectAllBanner =
    !selectAllMatching && allOnPageSelected && totalMatching > pageIds.length;

  const selection: BulkSelection = useMemo(
    () =>
      selectAllMatching
        ? { mode: 'allMatching', filters, excludedIds: Array.from(excludedIds) }
        : { mode: 'ids', ids: Array.from(selectedIds) },
    [selectAllMatching, filters, excludedIds, selectedIds]
  );

  return {
    selection,
    selectedCount,
    isRowSelected,
    toggleRow,
    allOnPageSelected,
    someOnPageSelected,
    toggleAllOnPage,
    showSelectAllBanner,
    selectAllMatchingFiltered,
    reset,
  };
}
```

```tsx
// hooks/useDocumentMutations.ts
import { useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { archiveDocuments, unarchiveDocuments, deleteDocuments } from '../api/documents';
import type { BulkSelection } from '../types';

const DELETE_GRACE_MS = 6000;

// Archive is server-reversible: fire immediately, offer a real Undo that calls
// the reverse endpoint. This matches "recoverable with effort" in the pattern
// table — the mistake has a fix, so it doesn't need a gate up front.
export function useArchiveWithUndo(onSettled: () => void) {
  const queryClient = useQueryClient();
  const [pendingUndo, setPendingUndo] = useState<{ selection: BulkSelection; count: number } | null>(null);

  const archive = useCallback(async (selection: BulkSelection, count: number) => {
    await archiveDocuments(selection);
    queryClient.invalidateQueries({ queryKey: ['documents'] });
    onSettled();
    setPendingUndo({ selection, count });
  }, [queryClient, onSettled]);

  const undo = useCallback(async () => {
    if (!pendingUndo) return;
    await unarchiveDocuments(pendingUndo.selection);
    queryClient.invalidateQueries({ queryKey: ['documents'] });
    setPendingUndo(null);
  }, [pendingUndo, queryClient]);

  const dismissUndo = useCallback(() => setPendingUndo(null), []);

  return { archive, pendingUndo, undo, dismissUndo };
}

// Delete has no reverse mutation, so Undo can't mean "reverse it" — it means
// "the request was never sent." The mutation is held behind a timer; Undo just
// clears the timer. Nothing destructive happens until the grace window elapses.
export function useDeleteWithGracePeriod(onSettled: () => void) {
  const queryClient = useQueryClient();
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [pendingDelete, setPendingDelete] = useState<{ selection: BulkSelection; count: number } | null>(null);

  const requestDelete = useCallback((selection: BulkSelection, count: number) => {
    setPendingDelete({ selection, count });
    timeoutRef.current = setTimeout(async () => {
      await deleteDocuments(selection);
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      setPendingDelete(null);
      onSettled();
    }, DELETE_GRACE_MS);
  }, [queryClient, onSettled]);

  const cancelDelete = useCallback(() => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = null;
    setPendingDelete(null);
  }, []);

  return { requestDelete, pendingDelete, cancelDelete, graceMs: DELETE_GRACE_MS };
}
```

```tsx
// components/ConfirmDeleteDialog.tsx
import { useState } from 'react';
import type { Document } from '../types';

interface Props {
  count: number;
  sampleTitles: string[]; // titles of a few selected documents, for grounding
  onCancel: () => void;
  onConfirm: () => void;
}

// Bulk delete always names the count (fixed-value inspection: "Are you sure?"
// asks about resolve, "47 documents including..." asks about facts). Above the
// threshold, the confirm button stays disabled until the user types DELETE —
// reproducing the phrase is what makes it non-reflexive, the same mechanism as
// GitHub's "type the repo name," adapted for a set with no single name.
const TYPE_TO_CONFIRM_THRESHOLD = 10;

export function ConfirmDeleteDialog({ count, sampleTitles, onCancel, onConfirm }: Props) {
  const requiresTyping = count > TYPE_TO_CONFIRM_THRESHOLD;
  const [typed, setTyped] = useState('');
  const canConfirm = !requiresTyping || typed === 'DELETE';

  const sampleText =
    sampleTitles.length > 0
      ? `Including “${sampleTitles.slice(0, 3).join('”, “')}”${
          count > sampleTitles.slice(0, 3).length ? `, and ${count - sampleTitles.slice(0, 3).length} more.` : '.'
        }`
      : null;

  return (
    <div
      role="alertdialog"
      aria-modal="true"
      aria-labelledby="delete-dialog-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
    >
      <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl">
        <h2 id="delete-dialog-title" className="text-lg font-semibold text-gray-900">
          Delete {count.toLocaleString()} document{count === 1 ? '' : 's'}?
        </h2>
        {sampleText && <p className="mt-2 text-sm text-gray-600">{sampleText}</p>}
        <p className="mt-2 text-sm text-gray-600">
          This cannot be undone once the {6}-second grace period ends.
        </p>

        {requiresTyping && (
          <div className="mt-4">
            <label htmlFor="confirm-delete-input" className="block text-sm font-medium text-gray-700">
              Type <span className="font-mono font-semibold">DELETE</span> to confirm
            </label>
            <input
              id="confirm-delete-input"
              type="text"
              value={typed}
              onChange={e => setTyped(e.target.value)}
              autoComplete="off"
              className="mt-1 w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-red-500 focus:outline-none focus:ring-1 focus:ring-red-500"
            />
          </div>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!canConfirm}
            aria-disabled={!canConfirm}
            onClick={onConfirm}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-red-300"
          >
            Delete forever
          </button>
        </div>
        {requiresTyping && !canConfirm && (
          <p className="mt-2 text-xs text-gray-500">Delete stays disabled until you type DELETE exactly.</p>
        )}
      </div>
    </div>
  );
}
```

```tsx
// components/Toast.tsx
interface Props {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  onDismiss: () => void;
}

export function Toast({ message, actionLabel, onAction, onDismiss }: Props) {
  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-4 rounded-lg bg-gray-900 px-4 py-3 text-sm text-white shadow-lg"
    >
      <span>{message}</span>
      {actionLabel && onAction && (
        <button type="button" onClick={onAction} className="font-semibold text-blue-300 hover:text-blue-200">
          {actionLabel}
        </button>
      )}
      <button type="button" onClick={onDismiss} aria-label="Dismiss" className="text-gray-400 hover:text-white">
        ✕
      </button>
    </div>
  );
}
```

```tsx
// components/BulkActionsBar.tsx
import { useState } from 'react';
import type { Document } from '../types';
import type { BulkSelection } from '../types';
import { ConfirmDeleteDialog } from './ConfirmDeleteDialog';
import { Toast } from './Toast';
import { useArchiveWithUndo, useDeleteWithGracePeriod } from '../hooks/useDocumentMutations';

interface Props {
  selection: BulkSelection;
  selectedCount: number;
  sampleSelectedDocs: Document[]; // visible selected rows, for the delete dialog + toast copy
  onClearSelection: () => void;
}

export function BulkActionsBar({ selection, selectedCount, sampleSelectedDocs, onClearSelection }: Props) {
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const { archive, pendingUndo, undo, dismissUndo } = useArchiveWithUndo(onClearSelection);
  const { requestDelete, pendingDelete, cancelDelete } = useDeleteWithGracePeriod(onClearSelection);

  if (selectedCount === 0) return null;

  const handleArchive = () => {
    archive(selection, selectedCount);
  };

  const handleConfirmDelete = () => {
    setShowDeleteDialog(false);
    requestDelete(selection, selectedCount);
  };

  return (
    <>
      <div
        role="toolbar"
        aria-label="Bulk document actions"
        className="sticky top-0 z-10 flex items-center justify-between gap-4 border-b border-blue-200 bg-blue-50 px-4 py-3"
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-blue-900">
            {selectedCount.toLocaleString()} document{selectedCount === 1 ? '' : 's'} selected
          </span>
          <button type="button" onClick={onClearSelection} className="text-sm text-blue-700 underline hover:text-blue-900">
            Clear selection
          </button>
        </div>

        {/* Delete is spatially and visually separated from Archive so a mis-click
            can't slide from a benign bulk action into an irreversible one. */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleArchive}
            className="rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Archive
          </button>
          <button
            type="button"
            onClick={() => setShowDeleteDialog(true)}
            className="rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50"
          >
            Delete
          </button>
        </div>
      </div>

      {showDeleteDialog && (
        <ConfirmDeleteDialog
          count={selectedCount}
          sampleTitles={sampleSelectedDocs.map(d => d.title)}
          onCancel={() => setShowDeleteDialog(false)}
          onConfirm={handleConfirmDelete}
        />
      )}

      {pendingUndo && (
        <Toast
          message={`Archived ${pendingUndo.count.toLocaleString()} document${pendingUndo.count === 1 ? '' : 's'}.`}
          actionLabel="Undo"
          onAction={undo}
          onDismiss={dismissUndo}
        />
      )}

      {pendingDelete && (
        <Toast
          message={`Deleting ${pendingDelete.count.toLocaleString()} document${pendingDelete.count === 1 ? '' : 's'}…`}
          actionLabel="Undo"
          onAction={cancelDelete}
          onDismiss={cancelDelete}
        />
      )}
    </>
  );
}
```

```tsx
// components/DocumentsTable.tsx  (integration example — wiring, not the full table)
import type { Document, DocumentFilters } from '../types';
import { useBulkSelection } from '../hooks/useBulkSelection';
import { BulkActionsBar } from './BulkActionsBar';

interface Props {
  documents: Document[]; // current page, up to 50 rows
  totalMatching: number; // total documents matching current filters, across all pages
  filters: DocumentFilters;
}

export function DocumentsTable({ documents, totalMatching, filters }: Props) {
  const pageIds = documents.map(d => d.id);
  const {
    selection,
    selectedCount,
    isRowSelected,
    toggleRow,
    allOnPageSelected,
    someOnPageSelected,
    toggleAllOnPage,
    showSelectAllBanner,
    selectAllMatchingFiltered,
    reset,
  } = useBulkSelection({ pageIds, totalMatching, filters });

  const sampleSelectedDocs = documents.filter(d => isRowSelected(d.id)).slice(0, 3);

  return (
    <div>
      <BulkActionsBar
        selection={selection}
        selectedCount={selectedCount}
        sampleSelectedDocs={sampleSelectedDocs}
        onClearSelection={reset}
      />

      {showSelectAllBanner && (
        <div className="flex items-center justify-center gap-2 bg-gray-50 px-4 py-2 text-sm text-gray-700">
          <span>All {documents.length} documents on this page are selected.</span>
          <button type="button" onClick={selectAllMatchingFiltered} className="font-semibold text-blue-700 hover:text-blue-900">
            Select all {totalMatching.toLocaleString()} documents matching your filters
          </button>
        </div>
      )}

      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-gray-200">
            <th className="w-10 px-4 py-2">
              <input
                type="checkbox"
                checked={allOnPageSelected}
                ref={el => { if (el) el.indeterminate = someOnPageSelected; }}
                onChange={toggleAllOnPage}
                aria-label="Select all documents on this page"
              />
            </th>
            <th className="px-4 py-2 font-medium text-gray-600">Title</th>
            <th className="px-4 py-2 font-medium text-gray-600">Owner</th>
            <th className="px-4 py-2 font-medium text-gray-600">Updated</th>
          </tr>
        </thead>
        <tbody>
          {documents.map(doc => (
            <tr key={doc.id} className="border-b border-gray-100 hover:bg-gray-50">
              <td className="px-4 py-2">
                <input
                  type="checkbox"
                  checked={isRowSelected(doc.id)}
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
    </div>
  );
}
```

★ Insight ─────────────────────────────────────
- The header checkbox intentionally never says "all 3,482 selected" by itself — it only ever reflects the current page, and the banner is a separate, explicit click. That's the fix for the "select all silently means everything" trap called out in the prompt's "thousands" detail.
- `sampleSelectedDocs` only comes from `documents` (the rendered page), so in "all matching" mode the dialog still shows real titles rather than fabricating them — if none of the sample happens to be visible, the dialog gracefully drops to just the count.
─────────────────────────────────────────────────

**Closing note (per poka-yoke:ux):**
- **Made impossible (Control):** an ambiguous selection payload (the `BulkSelection` union can't express "ids AND allMatching" simultaneously); a delete firing before the grace period or dialog resolve; the header checkbox implying more than the visible page is selected; the Delete confirm button being clickable before the typed phrase matches, for large batches.
- **Left possible on purpose:** small deletes (≤10) skip the type-to-confirm step — a named dialog is enough friction there, and gating every delete equally would just teach people to type DELETE reflexively. Archive has no dialog at all, since it's server-reversible and gets a real Undo instead.
- **Backend dependency, stated honestly:** the delete grace period is a frontend device standing in for what should really be a backend soft-delete/trash with retention (the strongest device in the ladder). If the API can be made soft-delete, `deleteDocuments` becomes reversible like archive and this whole delayed-commit path can be deleted.