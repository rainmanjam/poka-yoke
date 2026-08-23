Using **poka-yoke:ux** — the destructive bulk action across thousands of rows is exactly its domain.

`★ Insight ─────────────────────────────────────`
The crux of this feature isn't the bar — it's that **selection cannot be an array of IDs**. With thousands of matches, "select all" is a *query descriptor*, not a list. Modelling it as `string[]` forces one of two bugs: fetch 3,412 IDs to the client, or silently send only the 50 on screen.

Second: a selection is only meaningful *relative to a filter*. If the user selects-all-matching, then changes the search box, the old selection now describes a different set. Binding the filter's identity into the selection state makes acting on a stale one unrepresentable.
`─────────────────────────────────────────────────`

---

## `types.ts`

```ts
export type DocumentId = string & { readonly __brand: 'DocumentId' };

export interface Document {
  id: DocumentId;
  title: string;
  updatedAt: string; // ISO 8601
  ownerName: string;
}

/** Everything that narrows the result set. Serialized into a QueryKey. */
export interface DocumentFilter {
  search?: string;
  ownerId?: string;
  status?: 'active' | 'archived';
  updatedAfter?: string;
}

export interface DocumentPage {
  items: Document[];
  page: number;
  pageSize: number;
  /** Total matching the filter — can be in the thousands. */
  total: number;
}

/**
 * Stable identity of "what the user is currently looking at".
 * Two filters that produce the same result set must produce the same key.
 */
export type QueryKey = string & { readonly __brand: 'QueryKey' };

export function toQueryKey(filter: DocumentFilter): QueryKey {
  // Sort keys so property order can't produce two keys for one filter.
  const normalized = Object.fromEntries(
    Object.entries(filter)
      .filter(([, v]) => v !== undefined && v !== '')
      .sort(([a], [b]) => a.localeCompare(b)),
  );
  return JSON.stringify(normalized) as QueryKey;
}
```

---

## `selection.ts` — the state machine

```ts
import type { DocumentId, DocumentFilter, QueryKey } from './types';

/**
 * Two modes, and only two. Note what is NOT here: a `DocumentId[]` of everything
 * matching. In `allMatching` the selection is a *description* of a set the client
 * has never enumerated, plus the rows the user has since un-ticked.
 *
 * `queryKey` is carried in the state itself. Combined with the reducer below, a
 * selection made under one filter cannot be applied under another.
 */
export type Selection =
  | { readonly mode: 'include'; readonly queryKey: QueryKey; readonly ids: ReadonlySet<DocumentId> }
  | { readonly mode: 'allMatching'; readonly queryKey: QueryKey; readonly excluded: ReadonlySet<DocumentId> };

export const emptySelection = (queryKey: QueryKey): Selection => ({
  mode: 'include',
  queryKey,
  ids: new Set(),
});

export type SelectionAction =
  | { type: 'toggleRow'; id: DocumentId; selected: boolean }
  | { type: 'toggleRange'; ids: readonly DocumentId[]; selected: boolean }
  | { type: 'togglePage'; pageIds: readonly DocumentId[]; selected: boolean }
  | { type: 'selectAllMatching' }
  | { type: 'clear' };

/**
 * Every action carries the queryKey that was live when the user acted. If it
 * doesn't match the stored one, the filter changed underneath and the reducer
 * resets before applying. There is no code path that mutates a stale selection —
 * that's rung 1, not a "remember to clear selection on filter change" comment.
 */
export function selectionReducer(
  state: Selection,
  action: SelectionAction & { queryKey: QueryKey },
): Selection {
  const base: Selection =
    state.queryKey === action.queryKey ? state : emptySelection(action.queryKey);

  switch (action.type) {
    case 'clear':
      return emptySelection(action.queryKey);

    case 'selectAllMatching':
      return { mode: 'allMatching', queryKey: action.queryKey, excluded: new Set() };

    case 'toggleRow':
      return applyIds(base, [action.id], action.selected);

    case 'toggleRange':
      return applyIds(base, action.ids, action.selected);

    case 'togglePage':
      // Un-ticking the header while in allMatching means "start over", not
      // "exclude these 50" — otherwise the count stays at 3,362 and reads as a bug.
      if (base.mode === 'allMatching' && !action.selected) {
        return emptySelection(action.queryKey);
      }
      return applyIds(base, action.pageIds, action.selected);
  }
}

function applyIds(state: Selection, ids: readonly DocumentId[], selected: boolean): Selection {
  if (state.mode === 'include') {
    const next = new Set(state.ids);
    for (const id of ids) (selected ? next.add(id) : next.delete(id));
    return { ...state, ids: next };
  }
  const next = new Set(state.excluded);
  for (const id of ids) (selected ? next.delete(id) : next.add(id));
  return { ...state, excluded: next };
}

// ---- derived state (pure, no memo needed at these sizes) ----

export function isRowSelected(s: Selection, id: DocumentId): boolean {
  return s.mode === 'include' ? s.ids.has(id) : !s.excluded.has(id);
}

/** `total` is the live total from the current page response. */
export function selectedCount(s: Selection, total: number): number {
  return s.mode === 'include' ? s.ids.size : Math.max(0, total - s.excluded.size);
}

export function headerCheckboxState(
  s: Selection,
  pageIds: readonly DocumentId[],
): 'checked' | 'indeterminate' | 'unchecked' {
  if (pageIds.length === 0) return 'unchecked';
  const n = pageIds.filter((id) => isRowSelected(s, id)).length;
  if (n === 0) return 'unchecked';
  return n === pageIds.length ? 'checked' : 'indeterminate';
}

/** Show the "select all N matching" banner only when the page is fully ticked. */
export function canEscalateToAllMatching(
  s: Selection,
  pageIds: readonly DocumentId[],
  total: number,
): boolean {
  return (
    s.mode === 'include' &&
    pageIds.length > 0 &&
    total > pageIds.length &&
    pageIds.every((id) => s.ids.has(id))
  );
}

// ---- the wire format ----

export type BulkTarget =
  | { mode: 'include'; ids: DocumentId[] }
  | { mode: 'allMatching'; filter: DocumentFilter; excludedIds: DocumentId[] };

export function toBulkTarget(s: Selection, filter: DocumentFilter): BulkTarget {
  return s.mode === 'include'
    ? { mode: 'include', ids: [...s.ids] }
    : { mode: 'allMatching', filter, excludedIds: [...s.excluded] };
}
```

---

## `api.ts`

```ts
import type { DocumentFilter, DocumentPage } from './types';
import type { BulkTarget } from './selection';

export interface BulkRequest {
  target: BulkTarget;
  /**
   * The count the user was shown at the moment they confirmed. The server
   * recounts and refuses if reality drifted — so "you saw 3,412" can never
   * become "we deleted 9,000" because a colleague uploaded in between.
   */
  expectedCount: number;
  /** Survives double-click, refresh mid-flight, and network retry. */
  idempotencyKey: string;
}

export interface BulkResult {
  affected: number;
  /** Present when the operation is reversible. Null means it isn't. */
  undoToken: string | null;
}

export class CountMismatchError extends Error {
  constructor(readonly expected: number, readonly actual: number) {
    super(`Expected ${expected} documents, found ${actual}. Nothing was changed.`);
    this.name = 'CountMismatchError';
  }
}

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (res.status === 409) {
    const { expected, actual } = await res.json();
    throw new CountMismatchError(expected, actual);
  }
  if (!res.ok) {
    throw new Error((await res.text()) || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export const fetchDocuments = async (filter: DocumentFilter, page: number): Promise<DocumentPage> => {
  const qs = new URLSearchParams({ page: String(page), pageSize: '50' });
  for (const [k, v] of Object.entries(filter)) if (v) qs.set(k, String(v));
  const res = await fetch(`/api/documents?${qs}`);
  if (!res.ok) throw new Error('Failed to load documents');
  return res.json();
};

export const bulkArchive = (req: BulkRequest) => post<BulkResult>('/api/documents/bulk-archive', req);
export const bulkDelete = (req: BulkRequest) => post<BulkResult>('/api/documents/bulk-delete', req);
export const undoBulk = (undoToken: string) => post<{ restored: number }>('/api/documents/bulk-undo', { undoToken });
```

---

## `useBulkAction.ts`

```ts
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { bulkArchive, bulkDelete, undoBulk, CountMismatchError, type BulkRequest, type BulkResult } from './api';
import type { DocumentFilter } from './types';
import { toBulkTarget, type Selection } from './selection';

export type BulkVerb = 'archive' | 'delete';

const RUNNERS: Record<BulkVerb, (r: BulkRequest) => Promise<BulkResult>> = {
  archive: bulkArchive,
  delete: bulkDelete,
};

const PAST_TENSE: Record<BulkVerb, string> = { archive: 'Archived', delete: 'Moved to trash' };

interface Args {
  verb: BulkVerb;
  selection: Selection;
  filter: DocumentFilter;
  /** Count as rendered in the bar — the number the user actually read. */
  expectedCount: number;
}

export function useBulkAction(onSettled: () => void) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: ({ verb, selection, filter, expectedCount }: Args) =>
      RUNNERS[verb]({
        target: toBulkTarget(selection, filter),
        expectedCount,
        // One key per attempt. A retry of *this* attempt is a no-op server-side;
        // a deliberate second click is a new key and a real second operation.
        idempotencyKey: crypto.randomUUID(),
      }).then((result) => ({ result, verb })),

    onSuccess: ({ result, verb }) => {
      qc.invalidateQueries({ queryKey: ['documents'] });
      const label = `${PAST_TENSE[verb]} ${result.affected.toLocaleString()} document${result.affected === 1 ? '' : 's'}.`;

      if (!result.undoToken) {
        toast.success(label);
        return;
      }
      toast.success(label, {
        duration: 10_000,
        action: {
          label: 'Undo',
          onClick: () =>
            undoBulk(result.undoToken!)
              .then((r) => {
                qc.invalidateQueries({ queryKey: ['documents'] });
                toast.success(`Restored ${r.restored.toLocaleString()} documents.`);
              })
              .catch(() => toast.error('Undo failed. The documents are still in trash.')),
        },
      });
    },

    onError: (err: unknown) => {
      if (err instanceof CountMismatchError) {
        qc.invalidateQueries({ queryKey: ['documents'] });
        toast.error(
          `The set changed while you were deciding — it now matches ${err.actual.toLocaleString()} documents. Nothing was changed. Please re-check and try again.`,
          { duration: 12_000 },
        );
        return;
      }
      toast.error(err instanceof Error ? err.message : 'Something went wrong. Nothing was changed.');
    },

    onSettled,
  });
}
```

---

## `ConfirmDeleteDialog.tsx`

```tsx
import { useEffect, useId, useRef, useState } from 'react';

/** Above this, or for any select-all-matching, we make the user read the number. */
const TYPE_TO_CONFIRM_THRESHOLD = 25;

interface Props {
  open: boolean;
  count: number;
  /** True when the target is a filter, not an enumerated list. */
  isAllMatching: boolean;
  pending: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDeleteDialog({ open, count, isAllMatching, pending, onConfirm, onCancel }: Props) {
  const [typed, setTyped] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descId = useId();

  const mustType = isAllMatching || count > TYPE_TO_CONFIRM_THRESHOLD;
  const expected = String(count);
  const armed = !pending && (!mustType || typed.trim() === expected);

  useEffect(() => {
    if (!open) return;
    setTyped('');
    // Focus the safe control, never the destructive one.
    (mustType ? inputRef : cancelRef).current?.focus();

    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !pending && onCancel();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, mustType, pending, onCancel]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
      >
        <h2 id={titleId} className="text-lg font-semibold text-slate-900">
          Move {count.toLocaleString()} document{count === 1 ? '' : 's'} to trash?
        </h2>

        {/* Name the consequence and the recovery, not "are you sure". */}
        <p id={descId} className="mt-2 text-sm text-slate-600">
          {isAllMatching
            ? 'This applies to every document matching your current filters, including ones not shown on this page. '
            : ''}
          They stay in trash for 30 days and can be restored from there. After 30 days they are
          permanently removed.
        </p>

        {mustType && (
          <label className="mt-4 block text-sm">
            <span className="text-slate-700">
              Type <span className="font-mono font-semibold text-slate-900">{expected}</span> to confirm
            </span>
            <input
              ref={inputRef}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              inputMode="numeric"
              autoComplete="off"
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-sm
                         focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-500/30"
            />
          </label>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <button
            ref={cancelRef}
            onClick={onCancel}
            disabled={pending}
            className="rounded-md px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100
                       focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!armed}
            aria-describedby={mustType && !armed ? `${titleId}-why` : undefined}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700
                       focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2
                       disabled:cursor-not-allowed disabled:bg-red-300"
          >
            {pending ? 'Moving…' : 'Move to trash'}
          </button>
        </div>

        {/* A disabled button with no stated reason is its own dead end. */}
        {mustType && !armed && !pending && (
          <p id={`${titleId}-why`} className="mt-2 text-right text-xs text-slate-500">
            Enter {expected} above to enable this button.
          </p>
        )}
      </div>
    </div>
  );
}
```

---

## `BulkActionsBar.tsx`

```tsx
import type { Selection } from './selection';

interface Props {
  count: number;
  selection: Selection;
  pending: boolean;
  onArchive: () => void;
  onDelete: () => void;
  onClear: () => void;
}

export function BulkActionsBar({ count, selection, pending, onArchive, onDelete, onClear }: Props) {
  if (count === 0) return null;

  return (
    <div
      role="region"
      aria-label="Bulk actions"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 shadow-[0_-2px_12px_rgba(0,0,0,0.08)] backdrop-blur"
    >
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
        {/* Announce the scale — this is the fixed-value inspection, not the dialog. */}
        <p aria-live="polite" className="text-sm font-medium text-slate-900">
          {count.toLocaleString()} document{count === 1 ? '' : 's'} selected
          {selection.mode === 'allMatching' && (
            <span className="ml-1 font-normal text-slate-500">(all matching your filters)</span>
          )}
        </p>

        <button
          onClick={onClear}
          disabled={pending}
          className="text-sm text-slate-500 underline-offset-2 hover:text-slate-900 hover:underline
                     focus:outline-none focus:ring-2 focus:ring-slate-400 disabled:opacity-50"
        >
          Clear selection
        </button>

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={onArchive}
            disabled={pending}
            className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700
                       hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-slate-400
                       disabled:cursor-not-allowed disabled:opacity-50"
          >
            Archive
          </button>

          {/* Separated by a spacer and styled distinctly — never adjacent-and-identical. */}
          <div className="mx-1 h-6 w-px bg-slate-200" aria-hidden="true" />

          <button
            onClick={onDelete}
            disabled={pending}
            className="rounded-md border border-red-200 bg-white px-4 py-2 text-sm font-medium text-red-700
                       hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500
                       disabled:cursor-not-allowed disabled:opacity-50"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
```

---

## `DocumentsTable.tsx` — wiring it together

```tsx
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchDocuments } from './api';
import { BulkActionsBar } from './BulkActionsBar';
import { ConfirmDeleteDialog } from './ConfirmDeleteDialog';
import { useBulkAction } from './useBulkAction';
import { toQueryKey, type Document, type DocumentFilter, type DocumentId } from './types';
import {
  canEscalateToAllMatching,
  emptySelection,
  headerCheckboxState,
  isRowSelected,
  selectedCount,
  selectionReducer,
  type SelectionAction,
} from './selection';

export function DocumentsTable({ filter }: { filter: DocumentFilter }) {
  const [page, setPage] = useState(1);
  const queryKey = useMemo(() => toQueryKey(filter), [filter]);

  const { data, isLoading } = useQuery({
    queryKey: ['documents', queryKey, page],
    queryFn: () => fetchDocuments(filter, page),
    placeholderData: (prev) => prev,
  });

  const [selection, rawDispatch] = useReducer(selectionReducer, queryKey, emptySelection);

  // Single choke point: no caller can dispatch without the live queryKey.
  const dispatch = useCallback(
    (action: SelectionAction) => rawDispatch({ ...action, queryKey }),
    [queryKey],
  );

  // Belt-and-braces: the reducer already resets on mismatch, but this clears the
  // bar the instant the filter changes rather than on the next interaction.
  useEffect(() => {
    rawDispatch({ type: 'clear', queryKey });
    setPage(1);
  }, [queryKey]);

  const docs: Document[] = data?.items ?? [];
  const total = data?.total ?? 0;
  const pageIds = useMemo(() => docs.map((d) => d.id), [docs]);
  const count = selectedCount(selection, total);

  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const bulk = useBulkAction(() => {
    setConfirmingDelete(false);
    dispatch({ type: 'clear' });
  });

  const run = (verb: 'archive' | 'delete') =>
    bulk.mutate({ verb, selection, filter, expectedCount: count });

  // ---- shift-click range selection ----
  const lastClicked = useRef<number | null>(null);
  const onRowToggle = (index: number, id: DocumentId, selected: boolean, shift: boolean) => {
    if (shift && lastClicked.current !== null) {
      const [from, to] = [lastClicked.current, index].sort((a, b) => a - b);
      dispatch({ type: 'toggleRange', ids: pageIds.slice(from, to + 1), selected });
    } else {
      dispatch({ type: 'toggleRow', id, selected });
    }
    lastClicked.current = index;
  };

  const header = headerCheckboxState(selection, pageIds);

  return (
    // Bottom padding keeps the last row reachable under the fixed bar.
    <div className={count > 0 ? 'pb-24' : ''}>
      <table className="w-full border-collapse text-sm">
        <thead className="border-b border-slate-200 bg-slate-50 text-left">
          <tr>
            <th scope="col" className="w-12 px-4 py-3">
              <Checkbox
                state={header}
                label={header === 'checked' ? 'Deselect all rows on this page' : 'Select all rows on this page'}
                onChange={(selected) => dispatch({ type: 'togglePage', pageIds, selected })}
              />
            </th>
            <th scope="col" className="px-4 py-3 font-medium text-slate-600">Title</th>
            <th scope="col" className="px-4 py-3 font-medium text-slate-600">Owner</th>
            <th scope="col" className="px-4 py-3 font-medium text-slate-600">Updated</th>
          </tr>
        </thead>

        <tbody className="divide-y divide-slate-100">
          {/* The escalation banner. Without it, ticking the header silently means
              "50 of 3,412" and the user assumes it means all of them. */}
          {canEscalateToAllMatching(selection, pageIds, total) && (
            <tr>
              <td colSpan={4} className="bg-blue-50 px-4 py-2 text-center text-sm text-blue-900">
                All {pageIds.length} documents on this page are selected.{' '}
                <button
                  onClick={() => dispatch({ type: 'selectAllMatching' })}
                  className="font-semibold underline underline-offset-2 hover:text-blue-700"
                >
                  Select all {total.toLocaleString()} documents matching your filters
                </button>
              </td>
            </tr>
          )}
          {selection.mode === 'allMatching' && (
            <tr>
              <td colSpan={4} className="bg-blue-50 px-4 py-2 text-center text-sm text-blue-900">
                All {count.toLocaleString()} documents matching your filters are selected.{' '}
                <button
                  onClick={() => dispatch({ type: 'clear' })}
                  className="font-semibold underline underline-offset-2 hover:text-blue-700"
                >
                  Select only this page instead
                </button>
              </td>
            </tr>
          )}

          {isLoading && (
            <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-500">Loading…</td></tr>
          )}
          {!isLoading && docs.length === 0 && (
            <tr><td colSpan={4} className="px-4 py-8 text-center text-slate-500">No documents match these filters.</td></tr>
          )}

          {docs.map((doc, i) => {
            const checked = isRowSelected(selection, doc.id);
            return (
              <tr key={doc.id} className={checked ? 'bg-blue-50/60' : 'hover:bg-slate-50'}>
                <td className="px-4 py-3">
                  <Checkbox
                    state={checked ? 'checked' : 'unchecked'}
                    label={`Select ${doc.title}`}
                    onChange={(sel, shift) => onRowToggle(i, doc.id, sel, shift)}
                  />
                </td>
                <td className="px-4 py-3 font-medium text-slate-900">{doc.title}</td>
                <td className="px-4 py-3 text-slate-600">{doc.ownerName}</td>
                <td className="px-4 py-3 text-slate-600">
                  <time dateTime={doc.updatedAt}>
                    {new Date(doc.updatedAt).toLocaleDateString()}
                  </time>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <Pagination page={page} total={total} pageSize={data?.pageSize ?? 50} onChange={setPage} />

      <BulkActionsBar
        count={count}
        selection={selection}
        pending={bulk.isPending}
        onArchive={() => run('archive')}
        onDelete={() => setConfirmingDelete(true)}
        onClear={() => dispatch({ type: 'clear' })}
      />

      <ConfirmDeleteDialog
        open={confirmingDelete}
        count={count}
        isAllMatching={selection.mode === 'allMatching'}
        pending={bulk.isPending}
        onConfirm={() => run('delete')}
        onCancel={() => setConfirmingDelete(false)}
      />
    </div>
  );
}

/** Tri-state checkbox — `indeterminate` is a DOM property, not an attribute. */
function Checkbox({
  state,
  label,
  onChange,
}: {
  state: 'checked' | 'indeterminate' | 'unchecked';
  label: string;
  onChange: (selected: boolean, shiftKey: boolean) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = state === 'indeterminate';
  }, [state]);

  return (
    <input
      ref={ref}
      type="checkbox"
      aria-label={label}
      checked={state === 'checked'}
      onChange={(e) => onChange(e.target.checked, (e.nativeEvent as MouseEvent).shiftKey)}
      className="h-4 w-4 cursor-pointer rounded border-slate-300 text-blue-600
                 focus:ring-2 focus:ring-blue-500 focus:ring-offset-1"
    />
  );
}

function Pagination({ page, total, pageSize, onChange }: {
  page: number; total: number; pageSize: number; onChange: (p: number) => void;
}) {
  const lastPage = Math.max(1, Math.ceil(total / pageSize));
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between px-4 py-4 text-sm">
      <span className="text-slate-600">
        Page {page} of {lastPage.toLocaleString()} · {total.toLocaleString()} documents
      </span>
      <div className="flex gap-2">
        <button
          onClick={() => onChange(page - 1)}
          disabled={page <= 1}
          className="rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-50 disabled:opacity-40"
        >
          Previous
        </button>
        <button
          onClick={() => onChange(page + 1)}
          disabled={page >= lastPage}
          className="rounded-md border border-slate-300 px-3 py-1.5 hover:bg-slate-50 disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </nav>
  );
}
```

---

## Server contract you need to hold up

```
POST /api/documents/bulk-delete
{ target: {mode:"allMatching", filter:{...}, excludedIds:[...]}, expectedCount: 3412, idempotencyKey: "..." }

→ 200 { affected: 3412, undoToken: "..." }
→ 409 { expected: 3412, actual: 3418 }   // recount drifted; nothing mutated
```

Three things the server must do, or the client-side devices are decorative:
1. **Recount inside the transaction** and abort on mismatch — that's what makes `expectedCount` a device rather than a display value.
2. **Store the idempotency key** with the result; a replay returns the original result without re-applying.
3. **Re-apply the tenant/permission scope to `filter` server-side.** The client sends a filter, not a list — never trust it as an authorization boundary.

---

## What this shape makes impossible, and what it leaves open

**Impossible (rung 1):** sending 50 IDs when the user asked for 3,412 — `allMatching` has no ID list to truncate. Acting on a selection made under a different filter — the queryKey lives inside the state and the reducer resets on mismatch. Double-applying on double-click or a network retry — one idempotency key per attempt. Deleting a set that grew while the dialog was open — the server recounts against `expectedCount` and refuses.

**Rung 2 by choice:** the count in the bar and the banner. Showing "3,412" *before* the click is what actually prevents the mistake; the dialog is a second reading of the same number.

**Left possible on purpose:** Archive has no dialog at all. It's reversible with a 10-second undo, and gating a reversible action on every use is how you train people to click through the gate that matters. Delete keeps a dialog even though it's a soft-delete, because restoring 3,000 documents from trash is a chore even when it's possible — and it escalates to type-the-count (the number, not the word "delete") above 25 rows or for any select-all-matching, because typing a word is muscle memory while typing a number forces you to read it.

**The one thing I'd want your input on:** `TYPE_TO_CONFIRM_THRESHOLD = 25` in `ConfirmDeleteDialog.tsx` is a guess. It's a real tradeoff — too low and your power users copy-paste through it daily until it means nothing; too high and a 40-document accident sails past. If you know your usage distribution (what's the p90 bulk-delete size?), set it above that so the device only fires on genuinely unusual actions.