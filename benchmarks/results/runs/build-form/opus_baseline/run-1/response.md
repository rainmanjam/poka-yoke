Using **poka-yoke:ux** — bulk delete over a selection that can mean "4,312 rows you never saw" is exactly the destructive-action-with-blast-radius case.

★ Insight ─────────────────────────────────────
The hard part of this component isn't the bar, it's the selection type. A `Set<id>` can't express "all 4,312 matching, except these three" — so teams either cap select-all at the visible page (users complain) or accumulate thousands of IDs client-side (fragile, and the request blows up). The fix is a discriminated union: `include` mode carries IDs, `exclude` mode carries a filter plus the deselected IDs, and the server resolves it.

The second hazard is invisible: in `exclude` mode the selection is a *description*, not a list. If the search box changes while that selection is live, the same state now means a different set of documents. That's a silent-widening bug, and it's why the filter key lives inside the selection state below.
`─────────────────────────────────────────────────`

## `types.ts`

```ts
export type DocumentId = string;

export interface Document {
  id: DocumentId;
  title: string;
  updatedAt: string; // ISO 8601
  ownerName: string;
}

/** Everything that narrows the result set. Must round-trip to the server verbatim. */
export interface DocumentFilter {
  query?: string;
  ownerId?: string;
  updatedBefore?: string;
  updatedAfter?: string;
}

/**
 * Selection is a *description*, never a materialised list.
 *
 * - include: the user picked these rows. Size is bounded by what they clicked.
 * - exclude: the user picked "everything matching the filter", then unpicked a few.
 *   `snapshotAt` bounds the server-side resolve so documents created *after* the
 *   user made the choice are not swept up by a slow request.
 */
export type Selection =
  | { mode: 'include'; ids: ReadonlySet<DocumentId> }
  | { mode: 'exclude'; excludedIds: ReadonlySet<DocumentId>; snapshotAt: string };

export const EMPTY_SELECTION: Selection = { mode: 'include', ids: new Set() };

/** The wire shape. Symmetric with Selection so no translation logic can drift. */
export type BulkTarget =
  | { mode: 'include'; ids: DocumentId[] }
  | {
      mode: 'exclude';
      filter: DocumentFilter;
      excludedIds: DocumentId[];
      snapshotAt: string;
    };

export function toBulkTarget(
  selection: Selection,
  filter: DocumentFilter,
): BulkTarget {
  return selection.mode === 'include'
    ? { mode: 'include', ids: [...selection.ids] }
    : {
        mode: 'exclude',
        filter,
        excludedIds: [...selection.excludedIds],
        snapshotAt: selection.snapshotAt,
      };
}

export function isRowSelected(selection: Selection, id: DocumentId): boolean {
  return selection.mode === 'include'
    ? selection.ids.has(id)
    : !selection.excludedIds.has(id);
}

/**
 * Returns null when the count is genuinely unknown (exclude mode before the
 * server has reported a total). Callers must not fall back to 0 — a bulk
 * delete labelled "0 documents" that removes thousands is the whole hazard.
 */
export function selectionCount(
  selection: Selection,
  totalMatching: number | undefined,
): number | null {
  if (selection.mode === 'include') return selection.ids.size;
  if (totalMatching === undefined) return null;
  return Math.max(0, totalMatching - selection.excludedIds.size);
}

/** Stable identity for a filter. Any change to it invalidates a live selection. */
export function filterKey(filter: DocumentFilter): string {
  return JSON.stringify([
    filter.query ?? '',
    filter.ownerId ?? '',
    filter.updatedBefore ?? '',
    filter.updatedAfter ?? '',
  ]);
}
```

## `useDocumentSelection.ts`

```ts
import { useCallback, useMemo, useReducer } from 'react';
import {
  EMPTY_SELECTION,
  filterKey,
  isRowSelected,
  selectionCount,
  type DocumentFilter,
  type DocumentId,
  type Selection,
} from './types';

interface State {
  key: string;
  selection: Selection;
  /** Anchor for shift-click range selection, scoped to the current page. */
  anchorId: DocumentId | null;
}

type Action =
  | { type: 'reset'; key: string }
  | { type: 'clear' }
  | { type: 'toggleRow'; id: DocumentId }
  | { type: 'selectRange'; ids: DocumentId[]; selected: boolean }
  | { type: 'setPage'; pageIds: DocumentId[]; selected: boolean }
  | { type: 'selectAllMatching'; snapshotAt: string };

function init(key: string): State {
  return { key, selection: EMPTY_SELECTION, anchorId: null };
}

function withMembership(
  selection: Selection,
  ids: DocumentId[],
  selected: boolean,
): Selection {
  if (selection.mode === 'include') {
    const next = new Set(selection.ids);
    for (const id of ids) selected ? next.add(id) : next.delete(id);
    return { mode: 'include', ids: next };
  }
  // In exclude mode, "selected" means *absent* from the exclusion set.
  const next = new Set(selection.excludedIds);
  for (const id of ids) selected ? next.delete(id) : next.add(id);
  return { ...selection, excludedIds: next };
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'reset':
      return init(action.key);

    case 'clear':
      return { ...state, selection: EMPTY_SELECTION, anchorId: null };

    case 'toggleRow': {
      const selected = !isRowSelected(state.selection, action.id);
      return {
        ...state,
        selection: withMembership(state.selection, [action.id], selected),
        anchorId: action.id,
      };
    }

    case 'selectRange':
      return {
        ...state,
        selection: withMembership(state.selection, action.ids, action.selected),
      };

    case 'setPage':
      return {
        ...state,
        selection: withMembership(state.selection, action.pageIds, action.selected),
        anchorId: null,
      };

    case 'selectAllMatching':
      return {
        ...state,
        selection: {
          mode: 'exclude',
          excludedIds: new Set(),
          snapshotAt: action.snapshotAt,
        },
        anchorId: null,
      };
  }
}

export function useDocumentSelection(
  filter: DocumentFilter,
  pageIds: readonly DocumentId[],
  totalMatching: number | undefined,
) {
  const key = filterKey(filter);
  const [state, dispatch] = useReducer(reducer, key, init);

  // Device: a selection is only meaningful against the filter it was made under.
  // Reset during render rather than in an effect, so a stale selection is never
  // observable — not for one frame, and not by a mutation fired from an event
  // handler that ran before the effect flushed.
  if (state.key !== key) dispatch({ type: 'reset', key });
  const selection = state.key === key ? state.selection : EMPTY_SELECTION;

  const count = selectionCount(selection, totalMatching);

  const pageSelectedCount = useMemo(
    () => pageIds.filter((id) => isRowSelected(selection, id)).length,
    [pageIds, selection],
  );

  const toggleRow = useCallback(
    (id: DocumentId, event?: { shiftKey: boolean }) => {
      const anchor = state.anchorId;
      if (event?.shiftKey && anchor && anchor !== id) {
        const from = pageIds.indexOf(anchor);
        const to = pageIds.indexOf(id);
        if (from !== -1 && to !== -1) {
          const [lo, hi] = from < to ? [from, to] : [to, from];
          dispatch({
            type: 'selectRange',
            ids: pageIds.slice(lo, hi + 1) as DocumentId[],
            // Range-select extends the anchor's state; it never inverts row-by-row.
            selected: isRowSelected(selection, anchor),
          });
          return;
        }
      }
      dispatch({ type: 'toggleRow', id });
    },
    [pageIds, selection, state.anchorId],
  );

  return {
    selection,
    /** null = count not yet known. Do not coerce to 0. */
    count,
    isSelected: useCallback(
      (id: DocumentId) => isRowSelected(selection, id),
      [selection],
    ),
    pageAllSelected: pageIds.length > 0 && pageSelectedCount === pageIds.length,
    pageSomeSelected:
      pageSelectedCount > 0 && pageSelectedCount < pageIds.length,
    toggleRow,
    setPage: useCallback(
      (selected: boolean) =>
        dispatch({ type: 'setPage', pageIds: pageIds as DocumentId[], selected }),
      [pageIds],
    ),
    selectAllMatching: useCallback(
      () =>
        dispatch({
          type: 'selectAllMatching',
          snapshotAt: new Date().toISOString(),
        }),
      [],
    ),
    clear: useCallback(() => dispatch({ type: 'clear' }), []),
  };
}
```

## `api/documents.ts`

```ts
import type { BulkTarget, Document, DocumentFilter } from '../types';

export interface DocumentPage {
  documents: Document[];
  totalMatching: number;
  nextCursor: string | null;
}

export interface BulkResult {
  /** What the server actually touched. May differ from the client's estimate. */
  affectedCount: number;
  /** Present when the operation is reversible. Absent means no undo is offered. */
  undoToken?: string;
}

export class BulkActionError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function post<T>(
  path: string,
  body: unknown,
  idempotencyKey: string,
): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      // Device: the button is not the only submission path. A refresh mid-flight,
      // a back-button resubmit, or a TanStack retry all reach the server again.
      // The key makes the *operation* idempotent, not just the click.
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new BulkActionError(
      (await res.text()) || `Request failed (${res.status})`,
      res.status,
    );
  }
  return res.json() as Promise<T>;
}

export function fetchDocuments(
  filter: DocumentFilter,
  cursor: string | null,
  signal: AbortSignal,
): Promise<DocumentPage> {
  const params = new URLSearchParams({ limit: '50' });
  if (filter.query) params.set('query', filter.query);
  if (filter.ownerId) params.set('ownerId', filter.ownerId);
  if (filter.updatedBefore) params.set('updatedBefore', filter.updatedBefore);
  if (filter.updatedAfter) params.set('updatedAfter', filter.updatedAfter);
  if (cursor) params.set('cursor', cursor);
  return fetch(`/api/documents?${params}`, { signal }).then((r) => r.json());
}

export interface BulkRequest {
  target: BulkTarget;
  idempotencyKey: string;
}

export const archiveDocuments = ({ target, idempotencyKey }: BulkRequest) =>
  post<BulkResult>('/api/documents/bulk/archive', { target }, idempotencyKey);

/**
 * Soft delete. Documents move to Trash and are purged after 30 days.
 * There is deliberately no hard-delete endpoint reachable from bulk selection —
 * permanent removal is a single-document action inside Trash.
 */
export const trashDocuments = ({ target, idempotencyKey }: BulkRequest) =>
  post<BulkResult>('/api/documents/bulk/trash', { target }, idempotencyKey);

export const undoBulkAction = (undoToken: string) =>
  post<BulkResult>('/api/documents/bulk/undo', { undoToken }, undoToken);
```

## `useBulkDocumentActions.ts`

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  archiveDocuments,
  trashDocuments,
  undoBulkAction,
  type BulkRequest,
  type BulkResult,
} from './api/documents';
import { toBulkTarget, type DocumentFilter, type Selection } from './types';

const nf = new Intl.NumberFormat();
const plural = (n: number) => (n === 1 ? 'document' : 'documents');

export function useBulkDocumentActions(
  filter: DocumentFilter,
  onSettled: () => void,
) {
  const queryClient = useQueryClient();

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['documents'] });

  const undo = useMutation({
    mutationFn: undoBulkAction,
    onSuccess: (result) => {
      toast.success(`Restored ${nf.format(result.affectedCount)} ${plural(result.affectedCount)}.`);
      void invalidate();
    },
    onError: () =>
      toast.error('Could not undo. The documents are in Trash — restore them there.'),
  });

  const announce = (verb: string, result: BulkResult) => {
    const label = `${verb} ${nf.format(result.affectedCount)} ${plural(result.affectedCount)}.`;
    if (result.undoToken) {
      const token = result.undoToken;
      toast.success(label, {
        duration: 10_000,
        action: { label: 'Undo', onClick: () => undo.mutate(token) },
      });
    } else {
      toast.success(label);
    }
  };

  const run = (
    mutationFn: (req: BulkRequest) => Promise<BulkResult>,
    verb: string,
  ) =>
    useMutation({
      mutationFn,
      // The key lives in the variables, so TanStack's retries — and any manual
      // retry of the same attempt — reuse it. A fresh click mints a fresh key.
      retry: 2,
      onSuccess: (result) => {
        announce(verb, result);
        void invalidate();
        onSettled();
      },
      onError: (error: Error) => {
        // Selection is preserved on failure. Losing a 4,000-row selection to a
        // 500 is its own mistake — the user would have to rebuild it blind.
        toast.error(`Nothing was changed. ${error.message}`);
      },
    });

  /* eslint-disable react-hooks/rules-of-hooks -- `run` is called unconditionally, in order */
  const archive = run(archiveDocuments, 'Archived');
  const trash = run(trashDocuments, 'Moved to Trash');
  /* eslint-enable react-hooks/rules-of-hooks */

  const build = (selection: Selection): BulkRequest => ({
    target: toBulkTarget(selection, filter),
    idempotencyKey: crypto.randomUUID(),
  });

  return {
    archive: (selection: Selection) => archive.mutate(build(selection)),
    trash: (selection: Selection) => trash.mutate(build(selection)),
    isPending: archive.isPending || trash.isPending,
  };
}
```

★ Insight ─────────────────────────────────────
`useBulkDocumentActions` returns `isPending` as a single flag rather than per-action. That's intentional: while *any* bulk mutation is in flight, every action in the bar disables. Per-action pending states leave "Delete" live during an archive, and the two operations race over the same rows.

Also note `onError` does not clear the selection. Clearing on failure feels tidy and is actively hostile — a user who spent effort building a 4,000-row selection cannot reconstruct it after a transient 502.
`─────────────────────────────────────────────────`

## `ConfirmBulkDeleteDialog.tsx`

```tsx
import { useEffect, useId, useRef, useState } from 'react';

const nf = new Intl.NumberFormat();

interface Props {
  open: boolean;
  count: number;
  /** True when the selection is "all matching", not an enumerated list of rows. */
  isFilterScoped: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

/**
 * Type-to-confirm, where the token is the *count itself*.
 *
 * Typing "DELETE" can be done without reading anything. Typing "4312" cannot —
 * the user has to look at the number, which is the exact fact we need them to
 * register before a filter-scoped delete.
 */
export function ConfirmBulkDeleteDialog({
  open,
  count,
  isFilterScoped,
  onCancel,
  onConfirm,
}: Props) {
  const [typed, setTyped] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const titleId = useId();
  const descId = useId();
  const expected = String(count);
  const matches = typed.trim() === expected;

  useEffect(() => {
    if (open) {
      setTyped('');
      inputRef.current?.focus();
    }
  }, [open, count]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      onKeyDown={(e) => e.key === 'Escape' && onCancel()}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl"
      >
        <h2 id={titleId} className="text-lg font-semibold text-slate-900">
          Move {nf.format(count)} {count === 1 ? 'document' : 'documents'} to Trash?
        </h2>

        <p id={descId} className="mt-2 text-sm text-slate-600">
          {isFilterScoped
            ? 'This applies to every document matching your current filters, including ones not shown on this page. '
            : ''}
          Items in Trash can be restored for 30 days, then are permanently deleted.
        </p>

        <label className="mt-5 block text-sm font-medium text-slate-700">
          Type <span className="font-mono text-slate-900">{expected}</span> to confirm
          <input
            ref={inputRef}
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            inputMode="numeric"
            autoComplete="off"
            className="mt-1.5 w-full rounded-md border border-slate-300 px-3 py-2 font-mono
                       text-slate-900 focus:border-red-500 focus:outline-none focus:ring-2
                       focus:ring-red-500/30"
          />
        </label>

        <div className="mt-6 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            Cancel
          </button>
          <div className="flex flex-col items-end gap-1">
            <button
              type="button"
              onClick={onConfirm}
              disabled={!matches}
              className="rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white
                         hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              Move to Trash
            </button>
            {!matches && (
              <span className="text-xs text-slate-500">
                Enter {expected} to enable
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
```

## `BulkActionsBar.tsx`

```tsx
import { useEffect, useState } from 'react';
import { ConfirmBulkDeleteDialog } from './ConfirmBulkDeleteDialog';
import type { Selection } from './types';

const nf = new Intl.NumberFormat();

/**
 * Above this many documents, a soft delete stops being casually recoverable —
 * restoring 500 items from Trash is an afternoon. Below it, the undo toast is
 * a better device than a dialog. Tune to your Trash UI's restore ergonomics.
 */
const TYPED_CONFIRM_THRESHOLD = 25;

interface Props {
  selection: Selection;
  /** null when unknown — the bar must not guess. */
  count: number | null;
  totalMatching: number | undefined;
  pageSize: number;
  isPending: boolean;
  onSelectAllMatching: () => void;
  onClear: () => void;
  onArchive: () => void;
  onDelete: () => void;
}

export function BulkActionsBar({
  selection,
  count,
  totalMatching,
  pageSize,
  isPending,
  onSelectAllMatching,
  onClear,
  onArchive,
  onDelete,
}: Props) {
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !confirming) onClear();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [confirming, onClear]);

  if (count === 0) return null;

  const isFilterScoped = selection.mode === 'exclude';
  const countKnown = count !== null;
  const needsTypedConfirm =
    countKnown && (isFilterScoped || count > TYPED_CONFIRM_THRESHOLD);

  // Device: an action whose blast radius is unknown is not offered. This is the
  // window where the total-count query is still in flight — rare, but it is
  // exactly when a mis-click is unrecoverable.
  const blockedReason = !countKnown
    ? 'Counting matching documents…'
    : isPending
      ? 'Working…'
      : null;
  const disabled = blockedReason !== null;

  const canEscalate =
    selection.mode === 'include' &&
    totalMatching !== undefined &&
    count === pageSize &&
    totalMatching > pageSize;

  const handleDelete = () => (needsTypedConfirm ? setConfirming(true) : onDelete());

  return (
    <>
      <div
        role="region"
        aria-label="Bulk actions"
        className="fixed inset-x-0 bottom-6 z-40 mx-auto flex w-fit max-w-[calc(100vw-2rem)]
                   items-center gap-4 rounded-xl border border-slate-200 bg-white px-4 py-3
                   shadow-lg shadow-slate-900/10"
      >
        <div className="min-w-0">
          <p aria-live="polite" className="text-sm font-medium text-slate-900">
            {countKnown
              ? `${nf.format(count)} selected`
              : 'Counting matching documents…'}
            {isFilterScoped && countKnown && (
              <span className="ml-1.5 font-normal text-slate-500">
                (all matching your filters)
              </span>
            )}
          </p>
          {canEscalate && (
            <button
              type="button"
              onClick={onSelectAllMatching}
              className="mt-0.5 text-xs font-medium text-blue-600 hover:text-blue-700 hover:underline"
            >
              Select all {nf.format(totalMatching!)} matching documents
            </button>
          )}
        </div>

        <div className="h-8 w-px shrink-0 bg-slate-200" aria-hidden="true" />

        <button
          type="button"
          onClick={onClear}
          className="shrink-0 rounded-md px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100"
        >
          Clear
        </button>

        <button
          type="button"
          onClick={onArchive}
          disabled={disabled}
          title={blockedReason ?? undefined}
          className="shrink-0 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-800
                     hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Archive
        </button>

        {/* Spatial separation: the destructive action does not sit flush against
            Archive, is never the default focus, and is the only red control here. */}
        <div className="w-6 shrink-0" aria-hidden="true" />

        <button
          type="button"
          onClick={handleDelete}
          disabled={disabled}
          title={blockedReason ?? undefined}
          className="shrink-0 rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-sm
                     font-semibold text-red-700 hover:bg-red-100
                     disabled:cursor-not-allowed disabled:opacity-50"
        >
          Delete
        </button>
      </div>

      <ConfirmBulkDeleteDialog
        open={confirming && countKnown}
        count={count ?? 0}
        isFilterScoped={isFilterScoped}
        onCancel={() => setConfirming(false)}
        onConfirm={() => {
          setConfirming(false);
          onDelete();
        }}
      />
    </>
  );
}
```

## `DocumentsTable.tsx`

```tsx
import { useEffect, useRef, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { BulkActionsBar } from './BulkActionsBar';
import { fetchDocuments } from './api/documents';
import { useBulkDocumentActions } from './useBulkDocumentActions';
import { useDocumentSelection } from './useDocumentSelection';
import { filterKey, type DocumentFilter, type DocumentId } from './types';

const PAGE_SIZE = 50;
const dtf = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' });

export function DocumentsTable({ filter }: { filter: DocumentFilter }) {
  const [cursor, setCursor] = useState<string | null>(null);

  // Paging must not reset the selection — only filtering does.
  useEffect(() => setCursor(null), [filterKey(filter)]);

  const { data, isPending } = useQuery({
    queryKey: ['documents', filter, cursor],
    queryFn: ({ signal }) => fetchDocuments(filter, cursor, signal),
    placeholderData: keepPreviousData,
  });

  const documents = data?.documents ?? [];
  const pageIds = documents.map((d) => d.id);

  const sel = useDocumentSelection(filter, pageIds, data?.totalMatching);
  const actions = useBulkDocumentActions(filter, sel.clear);

  const headerRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (headerRef.current) headerRef.current.indeterminate = sel.pageSomeSelected;
  }, [sel.pageSomeSelected]);

  return (
    <div className="pb-28">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="w-12 px-4 py-3">
              <input
                ref={headerRef}
                type="checkbox"
                checked={sel.pageAllSelected}
                onChange={(e) => sel.setPage(e.target.checked)}
                disabled={documents.length === 0}
                aria-label={`Select all ${documents.length} documents on this page`}
                className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
              />
            </th>
            <th scope="col" className="px-4 py-3 font-medium">Title</th>
            <th scope="col" className="px-4 py-3 font-medium">Owner</th>
            <th scope="col" className="px-4 py-3 font-medium">Updated</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {documents.map((doc) => {
            const checked = sel.isSelected(doc.id);
            return (
              <tr
                key={doc.id}
                className={checked ? 'bg-blue-50/60' : 'hover:bg-slate-50'}
              >
                <td className="px-4 py-3">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {}}
                    onClick={(e) =>
                      sel.toggleRow(doc.id as DocumentId, { shiftKey: e.shiftKey })
                    }
                    aria-label={`Select ${doc.title}`}
                    className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                </td>
                <td className="max-w-md truncate px-4 py-3 font-medium text-slate-900">
                  {doc.title}
                </td>
                <td className="px-4 py-3 text-slate-600">{doc.ownerName}</td>
                <td className="px-4 py-3 text-slate-600">
                  <time dateTime={doc.updatedAt}>
                    {dtf.format(new Date(doc.updatedAt))}
                  </time>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {!isPending && documents.length === 0 && (
        <p className="px-4 py-12 text-center text-sm text-slate-500">
          No documents match these filters.
        </p>
      )}

      <div className="flex justify-end px-4 py-4">
        <button
          type="button"
          onClick={() => setCursor(data?.nextCursor ?? null)}
          disabled={!data?.nextCursor}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium
                     text-slate-700 hover:bg-slate-50 disabled:opacity-40"
        >
          Next {PAGE_SIZE}
        </button>
      </div>

      <BulkActionsBar
        selection={sel.selection}
        count={sel.count}
        totalMatching={data?.totalMatching}
        pageSize={PAGE_SIZE}
        isPending={actions.isPending}
        onSelectAllMatching={sel.selectAllMatching}
        onClear={sel.clear}
        onArchive={() => actions.archive(sel.selection)}
        onDelete={() => actions.trash(sel.selection)}
      />
    </div>
  );
}
```

---

### What this makes impossible, and what it leaves open

**Rung 1 — cannot be expressed.** A bulk action against an unknown blast radius: while `totalMatching` is unresolved, `count` is `null` and both buttons are disabled with a stated reason, rather than defaulting to `0`. A selection surviving a filter change: the reset happens during render, keyed on the filter, so a mutation fired from an event handler can never read a stale set. And there is no hard-delete on this path at all — `trashDocuments` soft-deletes; permanent removal lives in Trash, one document at a time.

**Rung 1 — cannot be done reflexively.** Delete over 25 rows, or any filter-scoped delete, requires typing the count. The token is the number itself precisely because it can't be satisfied without reading the fact we need registered. Under that threshold there's no dialog at all — just the undo toast, which is the stronger device for a recoverable action and doesn't train click-through blindness.

**Rung 2.** The bar names the count and says "all matching your filters" in exclude mode; `snapshotAt` bounds the server resolve so documents created during a slow request aren't swept in.

**Left possible on purpose.** Archive has no confirmation — it's trivially reversible and confirming it would be friction on the common path. Selection survives a failed mutation rather than clearing; a lost 4,000-row selection is unreconstructable. And the exclude-mode count is an estimate: the toast reports the server's `affectedCount`, which may differ if the data moved underneath. Showing the real number afterward beats pretending the estimate was exact.

**Two things this component assumes and does not enforce** — worth confirming they exist server-side: `Idempotency-Key` is honored on all three bulk endpoints, and the server re-authorizes every document the filter resolves to. A filter-scoped delete is the single easiest place to leak a permission check, because the client never names the rows.

`TYPED_CONFIRM_THRESHOLD` in `BulkActionsBar.tsx` is the one number here that's a genuine product call rather than a mechanical one — it's the point where restoring from Trash stops being a minute's work. I set 25 as a defensible default; if your Trash UI has multi-select restore, it should go higher.