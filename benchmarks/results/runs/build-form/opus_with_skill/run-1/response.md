Read the router, then `poka-yoke:ux` in full, plus `references/ux-patterns.md`, `references/hazard-catalog.md`, and `references/lang-typescript.md`. This is the "building, not reviewing" case, so here is the interface.

**Assumptions:** React 18 + TS (`strict`), Tailwind, TanStack Query, REST. Delete is a soft-delete to Trash with 30-day retention (a backend decision, and the single highest-leverage one here).

---

## `documents/types.ts`

```ts
// Branded IDs: a raw string from a URL param or a form can't be passed where a
// DocumentId is expected without going through a parse. (Hazard C3.)
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type DocumentId = Brand<string, "DocumentId">;
export type BulkOperationId = Brand<string, "BulkOperationId">;
export type UndoToken = Brand<string, "UndoToken">;
export type IdempotencyKey = Brand<string, "IdempotencyKey">;
export type FilterScopeKey = Brand<string, "FilterScopeKey">;

export const DocumentId = (s: string): DocumentId => s as DocumentId;
export const newIdempotencyKey = (): IdempotencyKey =>
  crypto.randomUUID() as IdempotencyKey;

export interface Document {
  readonly id: DocumentId;
  readonly title: string;
  readonly updatedAt: string; // ISO 8601, UTC (C9: never a naive local date)
  readonly ownerName: string;
}

export interface DocumentFilter {
  readonly q?: string;
  readonly ownerId?: string;
  readonly updatedAfter?: string;
}

/**
 * Stable identity for "the set of documents currently being looked at".
 * Selection is keyed on this, so a selection made under one filter can never be
 * acted on under another. Keys are built field-by-field, not by stringifying the
 * caller's object, so property order can't change the key.
 */
export const filterScopeKey = (f: DocumentFilter): FilterScopeKey =>
  JSON.stringify([f.q ?? "", f.ownerId ?? "", f.updatedAfter ?? ""]) as FilterScopeKey;

/** A list the type system knows is non-empty. */
export type NonEmpty<T> = readonly [T, ...T[]];
export const nonEmpty = <T>(xs: readonly T[]): NonEmpty<T> | null =>
  xs.length > 0 ? (xs as NonEmpty<T>) : null;

/**
 * What a bulk mutation acts on. Two variants, and neither one can express
 * "everything" by accident:
 *   - ids:    non-empty by type, so an empty selection cannot be submitted.
 *   - filter: carries expectedCount, so the server refuses if the real count
 *             drifted from the number the user actually read and confirmed.
 * (Hazard F2 — unbounded destructive operation.)
 */
export type BulkTarget =
  | { readonly kind: "ids"; readonly ids: NonEmpty<DocumentId> }
  | {
      readonly kind: "filter";
      readonly filter: DocumentFilter;
      readonly excludedIds: readonly DocumentId[];
      readonly expectedCount: number;
    };

export function assertNever(x: never): never {
  throw new Error(`Unhandled variant: ${JSON.stringify(x)}`);
}

const nf = new Intl.NumberFormat();
export const formatCount = (n: number) => nf.format(n);
```

## `documents/selection.ts`

```ts
import {
  type BulkTarget,
  type DocumentFilter,
  type DocumentId,
  type FilterScopeKey,
  type NonEmpty,
  assertNever,
  nonEmpty,
} from "./types";

/**
 * The two selection modes are genuinely different things and are modelled as
 * different variants rather than a boolean + a set of ids:
 *   include     — exactly these ids (what a header checkbox gives you: 50 rows)
 *   allMatching — every document matching the filter, minus explicit exclusions
 *                 (thousands; only reachable via a second, deliberate click)
 * Collapsing these into one shape is the classic "select all" trap.
 */
export type SelectionState =
  | { readonly mode: "none" }
  | {
      readonly mode: "include";
      readonly scope: FilterScopeKey;
      readonly ids: ReadonlySet<DocumentId>;
    }
  | {
      readonly mode: "allMatching";
      readonly scope: FilterScopeKey;
      readonly matchedCount: number;
      readonly excluded: ReadonlySet<DocumentId>;
    };

type Scoped = Extract<SelectionState, { scope: FilterScopeKey }>;

export type SelectionAction =
  | { type: "toggleRow"; scope: FilterScopeKey; id: DocumentId }
  | { type: "setRange"; scope: FilterScopeKey; ids: readonly DocumentId[]; selected: boolean }
  | { type: "togglePage"; scope: FilterScopeKey; pageIds: readonly DocumentId[] }
  | { type: "selectAllMatching"; scope: FilterScopeKey; matchedCount: number }
  | { type: "clear" };

export const emptySelection: SelectionState = { mode: "none" };

const freshInclude = (scope: FilterScopeKey): Scoped => ({
  mode: "include",
  scope,
  ids: new Set(),
});

export function selectionReducer(
  state: SelectionState,
  action: SelectionAction,
): SelectionState {
  if (action.type === "clear") return emptySelection;

  // Every mutation is scoped. If the filter moved on, we start from empty rather
  // than folding new clicks into a selection the user can no longer see.
  const base: Scoped =
    state.mode !== "none" && state.scope === action.scope ? state : freshInclude(action.scope);

  switch (action.type) {
    case "toggleRow":
      return applyRows(base, [action.id], !isSelected(base, action.id));

    case "setRange":
      return applyRows(base, action.ids, action.selected);

    case "togglePage": {
      const allOn = action.pageIds.every((id) => isSelected(base, id));
      return applyRows(base, action.pageIds, !allOn);
    }

    case "selectAllMatching":
      return {
        mode: "allMatching",
        scope: action.scope,
        matchedCount: action.matchedCount,
        excluded: new Set(),
      };

    default:
      return assertNever(action);
  }
}

function applyRows(state: Scoped, ids: readonly DocumentId[], selected: boolean): Scoped {
  if (state.mode === "allMatching") {
    const excluded = new Set(state.excluded);
    for (const id of ids) (selected ? excluded.delete(id) : excluded.add(id));
    return { ...state, excluded };
  }
  const next = new Set(state.ids);
  for (const id of ids) (selected ? next.add(id) : next.delete(id));
  return { ...state, ids: next };
}

export function isSelected(state: SelectionState, id: DocumentId): boolean {
  switch (state.mode) {
    case "none":
      return false;
    case "include":
      return state.ids.has(id);
    case "allMatching":
      return !state.excluded.has(id);
    default:
      return assertNever(state);
  }
}

/**
 * A selection that is guaranteed non-empty and guaranteed current. The bulk bar
 * takes this type, so "bar visible with nothing selected" and "bar acting on a
 * stale filter" are both unrepresentable rather than guarded by an `if`.
 */
export type ActiveSelection =
  | { readonly mode: "include"; readonly ids: NonEmpty<DocumentId>; readonly count: number }
  | {
      readonly mode: "allMatching";
      readonly filter: DocumentFilter;
      readonly excludedIds: readonly DocumentId[];
      readonly count: number;
    };

export function activeSelection(
  state: SelectionState,
  scope: FilterScopeKey,
  filter: DocumentFilter,
): ActiveSelection | null {
  if (state.mode === "none" || state.scope !== scope) return null;

  if (state.mode === "include") {
    const ids = nonEmpty([...state.ids]);
    return ids ? { mode: "include", ids, count: ids.length } : null;
  }

  const count = Math.max(0, state.matchedCount - state.excluded.size);
  if (count === 0) return null;
  return { mode: "allMatching", filter, excludedIds: [...state.excluded], count };
}

export function toTarget(s: ActiveSelection): BulkTarget {
  switch (s.mode) {
    case "include":
      return { kind: "ids", ids: s.ids };
    case "allMatching":
      // The ids are never enumerated client-side — 40,000 of them would be an
      // unbounded request body (F7). The server re-runs the filter.
      return {
        kind: "filter",
        filter: s.filter,
        excludedIds: s.excludedIds,
        expectedCount: s.count,
      };
    default:
      return assertNever(s);
  }
}
```

## `documents/api.ts`

```ts
import {
  type BulkOperationId,
  type BulkTarget,
  type Document,
  type DocumentFilter,
  type IdempotencyKey,
  type UndoToken,
} from "./types";

export const PAGE_SIZE = 50;

export interface DocumentPage {
  readonly items: readonly Document[];
  readonly total: number; // total matching the filter, not the page
}

export interface BulkReceipt {
  readonly operationId: BulkOperationId;
  readonly affectedCount: number;
  readonly undo: { readonly token: UndoToken; readonly expiresAt: string } | null;
}

/** The server re-ran the filter and got a different number than the user confirmed. */
export class CountChangedError extends Error {
  constructor(
    readonly expected: number,
    readonly actual: number,
  ) {
    super(`Expected ${expected} documents, filter now matches ${actual}`);
    this.name = "CountChangedError";
  }
}

export async function fetchDocuments(
  filter: DocumentFilter,
  page: number,
  signal?: AbortSignal,
): Promise<DocumentPage> {
  const params = new URLSearchParams({ page: String(page), pageSize: String(PAGE_SIZE) });
  if (filter.q) params.set("q", filter.q);
  if (filter.ownerId) params.set("ownerId", filter.ownerId);
  if (filter.updatedAfter) params.set("updatedAfter", filter.updatedAfter);

  const res = await fetch(`/api/documents?${params}`, { signal });
  if (!res.ok) throw new Error(`Failed to load documents (${res.status})`);
  return (await res.json()) as DocumentPage;
}

/**
 * idempotencyKey is a required parameter, not an option. A retried POST — by
 * react-query, by a double-click, by a flaky network — cannot archive twice.
 * The server must back this with a unique index on (user_id, idempotency_key)
 * reserved in the same transaction as the effect. (Hazard M2.)
 */
async function postBulk(
  path: string,
  body: unknown,
  idempotencyKey: IdempotencyKey,
): Promise<BulkReceipt> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(body),
  });

  if (res.status === 409) {
    const payload = (await res.json()) as { code?: string; expected?: number; actual?: number };
    if (payload.code === "count_changed") {
      throw new CountChangedError(payload.expected ?? 0, payload.actual ?? 0);
    }
  }
  if (!res.ok) throw new Error(`Bulk action failed (${res.status})`);
  return (await res.json()) as BulkReceipt;
}

export const bulkArchive = (a: { target: BulkTarget; idempotencyKey: IdempotencyKey }) =>
  postBulk("/api/documents/bulk/archive", { target: a.target }, a.idempotencyKey);

/** Moves to Trash. Recoverable for 30 days; the dialog says so honestly. */
export const bulkTrash = (a: { target: BulkTarget; idempotencyKey: IdempotencyKey }) =>
  postBulk("/api/documents/bulk/trash", { target: a.target }, a.idempotencyKey);

export const undoBulk = (a: {
  operationId: BulkOperationId;
  token: UndoToken;
  idempotencyKey: IdempotencyKey;
}) =>
  postBulk(
    `/api/documents/bulk/${a.operationId}/undo`,
    { token: a.token },
    a.idempotencyKey,
  );
```

## `documents/useBulkDocumentActions.ts`

```ts
import { useCallback, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import {
  type BulkReceipt,
  bulkArchive,
  bulkTrash,
  CountChangedError,
  undoBulk,
} from "./api";
import { type ActiveSelection, toTarget } from "./selection";
import { type IdempotencyKey, newIdempotencyKey } from "./types";

export type BulkAction = "archive" | "trash";

export interface CompletedOperation {
  readonly action: BulkAction;
  readonly receipt: BulkReceipt;
}

export function useBulkDocumentActions(onSettled?: () => void) {
  const qc = useQueryClient();
  const [completed, setCompleted] = useState<CompletedOperation | null>(null);
  const [countDrift, setCountDrift] = useState<CountChangedError | null>(null);

  const run = useMutation({
    mutationFn: (v: {
      action: BulkAction;
      selection: ActiveSelection;
      idempotencyKey: IdempotencyKey;
    }) => {
      const args = { target: toTarget(v.selection), idempotencyKey: v.idempotencyKey };
      return v.action === "archive" ? bulkArchive(args) : bulkTrash(args);
    },
    // Retries reuse `variables`, so the same idempotency key goes out every time.
    retry: (failures, error) => failures < 2 && !(error instanceof CountChangedError),
    onSuccess: (receipt, v) => {
      setCountDrift(null);
      setCompleted({ action: v.action, receipt });
      void qc.invalidateQueries({ queryKey: ["documents"] });
      onSettled?.();
    },
    onError: (error) => {
      // The selection is deliberately NOT cleared on failure — the user's work
      // survives so they can retry without re-selecting 4,000 rows.
      if (error instanceof CountChangedError) setCountDrift(error);
    },
  });

  const undo = useMutation({
    mutationFn: (op: CompletedOperation) => {
      if (!op.receipt.undo) throw new Error("This operation is not undoable");
      return undoBulk({
        operationId: op.receipt.operationId,
        token: op.receipt.undo.token,
        idempotencyKey: newIdempotencyKey(),
      });
    },
    onSuccess: () => {
      setCompleted(null);
      void qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const perform = useCallback(
    (action: BulkAction, selection: ActiveSelection) => {
      // One key per user intent, created here and carried through every retry.
      run.mutate({ action, selection, idempotencyKey: newIdempotencyKey() });
    },
    [run],
  );

  return {
    perform,
    pendingAction: run.isPending ? run.variables.action : null,
    error: run.error,
    countDrift,
    completed,
    dismissCompleted: () => setCompleted(null),
    undo: (op: CompletedOperation) => undo.mutate(op),
    isUndoing: undo.isPending,
  };
}
```

## `documents/BulkActionsBar.tsx`

```tsx
import { type ActiveSelection } from "./selection";
import { type BulkAction } from "./useBulkDocumentActions";
import { formatCount } from "./types";

interface Props {
  /** Non-empty and scope-current by type: this bar cannot render for zero rows. */
  selection: ActiveSelection;
  pendingAction: BulkAction | null;
  onArchive: () => void;
  onDelete: () => void;
  onClear: () => void;
}

export function BulkActionsBar({
  selection,
  pendingAction,
  onArchive,
  onDelete,
  onClear,
}: Props) {
  const busy = pendingAction !== null;
  const scale =
    selection.mode === "allMatching"
      ? `${formatCount(selection.count)} documents — everything matching this filter`
      : `${formatCount(selection.count)} document${selection.count === 1 ? "" : "s"} on this page`;

  return (
    <div
      role="region"
      aria-label="Bulk actions"
      className="fixed inset-x-0 bottom-6 z-40 mx-auto flex w-fit max-w-[calc(100vw-2rem)]
                 items-center gap-3 rounded-xl border border-slate-700 bg-slate-900/95 px-4 py-3
                 text-sm text-white shadow-2xl backdrop-blur
                 motion-safe:animate-in motion-safe:slide-in-from-bottom-2"
    >
      {/* Scale is stated in the bar itself, not only in a dialog nobody reads. */}
      <p aria-live="polite" className="whitespace-nowrap font-medium">
        {scale}
      </p>

      <span aria-hidden className="h-5 w-px bg-slate-700" />

      <button
        type="button"
        onClick={onArchive}
        disabled={busy}
        className="rounded-lg bg-white px-3 py-1.5 font-semibold text-slate-900
                   hover:bg-slate-100 focus-visible:outline focus-visible:outline-2
                   focus-visible:outline-offset-2 focus-visible:outline-white
                   disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pendingAction === "archive" ? "Archiving…" : "Archive"}
      </button>

      <button
        type="button"
        onClick={onClear}
        disabled={busy}
        className="rounded-lg px-3 py-1.5 text-slate-300 hover:text-white
                   focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2
                   focus-visible:outline-white disabled:opacity-60"
      >
        Clear selection
      </button>

      {/* Destructive action is spatially separated, styled differently, never the
          primary button, and never the default focus target. */}
      <span aria-hidden className="ml-4 h-5 w-px bg-slate-700" />

      <button
        type="button"
        onClick={onDelete}
        disabled={busy}
        className="ml-2 rounded-lg border border-red-500/60 px-3 py-1.5 font-semibold
                   text-red-300 hover:bg-red-500/10 hover:text-red-200
                   focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2
                   focus-visible:outline-red-400 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {pendingAction === "trash" ? "Deleting…" : "Delete"}
      </button>
    </div>
  );
}
```

## `documents/ConfirmBulkTrashDialog.tsx`

```tsx
import { useEffect, useId, useRef, useState } from "react";
import { formatCount } from "./types";

interface Props {
  open: boolean;
  count: number;
  /** Titles of selected rows visible on this page — names the objects, not just the number. */
  sampleTitles: readonly string[];
  isAllMatching: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ConfirmBulkTrashDialog({
  open,
  count,
  sampleTitles,
  isAllMatching,
  onCancel,
  onConfirm,
}: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [typed, setTyped] = useState("");
  const hintId = useId();

  useEffect(() => {
    const d = dialogRef.current;
    if (!d) return;
    if (open && !d.open) {
      setTyped("");
      d.showModal(); // native modal: focus trap + Esc, for free
    } else if (!open && d.open) {
      d.close();
    }
  }, [open]);

  // Typing the count is the fixed-value check: it cannot be satisfied without
  // reading the number. Reserved for bulk delete, never used for Archive.
  const matches = typed.replace(/\D/g, "") === String(count);

  const submit = () => {
    if (matches) onConfirm();
  };

  return (
    <dialog
      ref={dialogRef}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      onClose={onCancel}
      className="max-w-md rounded-2xl p-0 backdrop:bg-slate-900/60 backdrop:backdrop-blur-sm"
    >
      <form
        method="dialog"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="space-y-4 p-6"
      >
        <h2 className="text-lg font-semibold text-slate-900">
          Delete {formatCount(count)} document{count === 1 ? "" : "s"}?
        </h2>

        {sampleTitles.length > 0 && (
          <ul className="max-h-32 space-y-1 overflow-y-auto rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
            {sampleTitles.map((t) => (
              <li key={t} className="truncate">
                {t}
              </li>
            ))}
            {count > sampleTitles.length && (
              <li className="text-slate-500">
                and {formatCount(count - sampleTitles.length)} more
              </li>
            )}
          </ul>
        )}

        {isAllMatching && (
          <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
            This applies to every document matching the current filter, not just the
            50 shown on this page.
          </p>
        )}

        {/* Honest about reversibility. Overclaiming permanence trains disbelief. */}
        <p className="text-sm text-slate-600">
          They move to Trash and are permanently deleted after 30 days. You can restore
          them from Trash until then.
        </p>

        <div className="space-y-1">
          <label htmlFor="confirm-count" className="block text-sm font-medium text-slate-900">
            Type <span className="font-mono font-semibold">{count}</span> to confirm
          </label>
          <input
            id="confirm-count"
            inputMode="numeric"
            autoComplete="off"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            aria-describedby={hintId}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 font-mono
                       focus:border-slate-900 focus:outline-none"
          />
          <p id={hintId} className="text-xs text-slate-500">
            {matches ? "Ready to delete." : `Enter ${count} to enable the delete button.`}
          </p>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg px-4 py-2 font-medium text-slate-700 hover:bg-slate-100"
          >
            Cancel
          </button>
          {/* aria-disabled, not disabled: the button stays focusable so a screen
              reader reaches the reason it can't be pressed yet. */}
          <button
            type="submit"
            aria-disabled={!matches}
            aria-describedby={hintId}
            className={`rounded-lg px-4 py-2 font-semibold text-white ${
              matches ? "bg-red-600 hover:bg-red-700" : "cursor-not-allowed bg-red-300"
            }`}
          >
            Delete {formatCount(count)} document{count === 1 ? "" : "s"}
          </button>
        </div>
      </form>
    </dialog>
  );
}
```

## `documents/UndoToast.tsx`

```tsx
import { useEffect, useState } from "react";
import { type CompletedOperation } from "./useBulkDocumentActions";
import { formatCount } from "./types";

const WINDOW_MS = 10_000;

export function UndoToast({
  operation,
  isUndoing,
  onUndo,
  onDismiss,
}: {
  operation: CompletedOperation;
  isUndoing: boolean;
  onUndo: () => void;
  onDismiss: () => void;
}) {
  const [remaining, setRemaining] = useState(WINDOW_MS);

  useEffect(() => {
    setRemaining(WINDOW_MS);
    const started = performance.now();
    const id = window.setInterval(() => {
      const left = WINDOW_MS - (performance.now() - started);
      if (left <= 0) {
        window.clearInterval(id);
        onDismiss();
      } else {
        setRemaining(left);
      }
    }, 250);
    return () => window.clearInterval(id);
  }, [operation, onDismiss]);

  const verb = operation.action === "archive" ? "Archived" : "Moved to Trash";

  return (
    <div
      role="status"
      className="fixed bottom-6 left-1/2 z-50 flex -translate-x-1/2 items-center gap-4
                 rounded-xl bg-slate-900 px-4 py-3 text-sm text-white shadow-2xl"
    >
      <span>
        {verb} {formatCount(operation.receipt.affectedCount)} document
        {operation.receipt.affectedCount === 1 ? "" : "s"}.
      </span>
      {operation.receipt.undo && (
        <button
          type="button"
          onClick={onUndo}
          disabled={isUndoing}
          className="font-semibold text-sky-300 underline underline-offset-2
                     hover:text-sky-200 disabled:opacity-60"
        >
          {isUndoing ? "Undoing…" : `Undo (${Math.ceil(remaining / 1000)})`}
        </button>
      )}
    </div>
  );
}
```

## `documents/DocumentsTable.tsx`

```tsx
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { PAGE_SIZE, fetchDocuments } from "./api";
import { BulkActionsBar } from "./BulkActionsBar";
import { ConfirmBulkTrashDialog } from "./ConfirmBulkTrashDialog";
import { UndoToast } from "./UndoToast";
import {
  activeSelection,
  emptySelection,
  isSelected,
  selectionReducer,
} from "./selection";
import { useBulkDocumentActions } from "./useBulkDocumentActions";
import {
  type Document,
  type DocumentFilter,
  type DocumentId,
  filterScopeKey,
  formatCount,
} from "./types";

/** Below this, delete is undo-only. Above it, the count must be typed. */
const TYPE_TO_CONFIRM_ABOVE = 20;

export function DocumentsTable({ filter }: { filter: DocumentFilter }) {
  const [page, setPage] = useState(1);
  const scope = useMemo(() => filterScopeKey(filter), [filter]);
  const [selection, dispatch] = useReducer(selectionReducer, emptySelection);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const lastToggled = useRef<number | null>(null);

  const { data, isPending, isError, refetch } = useQuery({
    queryKey: ["documents", scope, page],
    queryFn: ({ signal }) => fetchDocuments(filter, page, signal),
    placeholderData: keepPreviousData,
  });

  useEffect(() => setPage(1), [scope]);

  const rows = data?.items ?? [];
  const total = data?.total ?? 0;
  const pageIds = useMemo(() => rows.map((r) => r.id), [rows]);

  // Returns null when nothing is selected OR when the selection predates the
  // current filter — so the bar simply isn't there, rather than being there and
  // acting on documents the user can no longer see.
  const active = activeSelection(selection, scope, filter);

  const bulk = useBulkDocumentActions(
    useCallback(() => dispatch({ type: "clear" }), []),
  );

  const pageAllSelected = pageIds.length > 0 && pageIds.every((id) => isSelected(selection, id));
  const pageSomeSelected = pageIds.some((id) => isSelected(selection, id));

  const headerRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (headerRef.current) {
      headerRef.current.indeterminate = pageSomeSelected && !pageAllSelected;
    }
  }, [pageSomeSelected, pageAllSelected]);

  const onRowToggle = (doc: Document, index: number, shiftKey: boolean) => {
    if (shiftKey && lastToggled.current !== null) {
      const [from, to] = [lastToggled.current, index].sort((a, b) => a - b);
      dispatch({
        type: "setRange",
        scope,
        ids: pageIds.slice(from, to + 1),
        selected: !isSelected(selection, doc.id),
      });
    } else {
      dispatch({ type: "toggleRow", scope, id: doc.id });
    }
    lastToggled.current = index;
  };

  const requestDelete = () => {
    if (!active) return;
    const needsTyping = active.mode === "allMatching" || active.count > TYPE_TO_CONFIRM_ABOVE;
    if (needsTyping) setConfirmingDelete(true);
    else bulk.perform("trash", active); // small + undoable: no dialog at all
  };

  const sampleTitles = useMemo(
    () => rows.filter((r) => isSelected(selection, r.id)).slice(0, 5).map((r) => r.title),
    [rows, selection],
  );

  if (isError) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-sm text-red-900">
        Couldn’t load documents.{" "}
        <button onClick={() => void refetch()} className="font-semibold underline">
          Try again
        </button>
      </div>
    );
  }

  return (
    <div className="relative pb-28">
      {/* The two scopes are never conflated: the header checkbox takes the 50 rows
          on screen, and selecting all N thousand takes a second, explicit click. */}
      {pageAllSelected && selection.mode === "include" && total > pageIds.length && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg bg-sky-50 px-4 py-2 text-sm text-sky-900">
          <span>All {pageIds.length} documents on this page are selected.</span>
          <button
            type="button"
            onClick={() => dispatch({ type: "selectAllMatching", scope, matchedCount: total })}
            className="font-semibold underline underline-offset-2"
          >
            Select all {formatCount(total)} documents matching this filter
          </button>
        </div>
      )}

      {selection.mode === "allMatching" && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg bg-amber-50 px-4 py-2 text-sm text-amber-900">
          <span>
            All {formatCount(Math.max(0, selection.matchedCount - selection.excluded.size))}{" "}
            documents matching this filter are selected.
          </span>
          <button
            type="button"
            onClick={() => dispatch({ type: "clear" })}
            className="font-semibold underline underline-offset-2"
          >
            Select only this page instead
          </button>
        </div>
      )}

      {bulk.countDrift && (
        <div className="mb-3 rounded-lg bg-red-50 px-4 py-2 text-sm text-red-900">
          Nothing was changed: this filter now matches{" "}
          {formatCount(bulk.countDrift.actual)} documents, not{" "}
          {formatCount(bulk.countDrift.expected)}. Review the list and try again.
        </div>
      )}

      <table className="w-full border-separate border-spacing-0 text-left text-sm">
        <thead>
          <tr className="text-slate-500">
            <th scope="col" className="w-10 border-b border-slate-200 px-3 py-2">
              <input
                ref={headerRef}
                type="checkbox"
                checked={pageAllSelected}
                onChange={() => dispatch({ type: "togglePage", scope, pageIds })}
                aria-label={`Select all ${pageIds.length} documents on this page`}
                className="size-4 rounded border-slate-300"
              />
            </th>
            <th scope="col" className="border-b border-slate-200 px-3 py-2 font-medium">Title</th>
            <th scope="col" className="border-b border-slate-200 px-3 py-2 font-medium">Owner</th>
            <th scope="col" className="border-b border-slate-200 px-3 py-2 font-medium">Updated</th>
          </tr>
        </thead>
        <tbody>
          {isPending &&
            Array.from({ length: 8 }, (_, i) => (
              <tr key={`skeleton-${i}`}>
                <td colSpan={4} className="border-b border-slate-100 px-3 py-3">
                  <div className="h-4 w-full animate-pulse rounded bg-slate-100" />
                </td>
              </tr>
            ))}

          {!isPending && rows.length === 0 && (
            <tr>
              <td colSpan={4} className="px-3 py-12 text-center text-slate-500">
                No documents match this filter.
              </td>
            </tr>
          )}

          {rows.map((doc, i) => {
            const checked = isSelected(selection, doc.id);
            return (
              <tr key={doc.id} className={checked ? "bg-sky-50/60" : "hover:bg-slate-50"}>
                <td className="border-b border-slate-100 px-3 py-2">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => undefined}
                    onClick={(e) => onRowToggle(doc, i, e.shiftKey)}
                    aria-label={`Select ${doc.title}`}
                    className="size-4 rounded border-slate-300"
                  />
                </td>
                <td className="border-b border-slate-100 px-3 py-2 font-medium text-slate-900">
                  {doc.title}
                </td>
                <td className="border-b border-slate-100 px-3 py-2 text-slate-600">
                  {doc.ownerName}
                </td>
                <td className="border-b border-slate-100 px-3 py-2 text-slate-600">
                  <time dateTime={doc.updatedAt}>
                    {new Date(doc.updatedAt).toLocaleDateString()}
                  </time>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <nav className="mt-4 flex items-center justify-between text-sm text-slate-600">
        <span>
          {formatCount(total)} document{total === 1 ? "" : "s"}
        </span>
        <span className="flex gap-2">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page === 1}
            className="rounded-lg border px-3 py-1.5 disabled:opacity-40"
          >
            Previous
          </button>
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={page * PAGE_SIZE >= total}
            className="rounded-lg border px-3 py-1.5 disabled:opacity-40"
          >
            Next
          </button>
        </span>
      </nav>

      {active && !bulk.completed && (
        <BulkActionsBar
          selection={active}
          pendingAction={bulk.pendingAction}
          onArchive={() => bulk.perform("archive", active)}
          onDelete={requestDelete}
          onClear={() => dispatch({ type: "clear" })}
        />
      )}

      {active && (
        <ConfirmBulkTrashDialog
          open={confirmingDelete}
          count={active.count}
          sampleTitles={sampleTitles}
          isAllMatching={active.mode === "allMatching"}
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={() => {
            setConfirmingDelete(false);
            bulk.perform("trash", active);
          }}
        />
      )}

      {bulk.completed && (
        <UndoToast
          operation={bulk.completed}
          isUndoing={bulk.isUndoing}
          onUndo={() => bulk.undo(bulk.completed!)}
          onDismiss={bulk.dismissCompleted}
        />
      )}
    </div>
  );
}
```

---

### What this shape makes impossible, and what it doesn't

**Control (rung 1).** A bulk action on zero rows can't be expressed — `ActiveSelection` and `NonEmpty<T>` are non-empty by type, so the bar can't render or submit empty. A selection can't outlive its filter: it's keyed on `FilterScopeKey`, so changing the filter makes `activeSelection` return `null` rather than silently deleting rows nobody can see. "50 on this page" and "all 4,312 matching" are separate union variants requiring separate clicks — the classic select-all trap has no spelling here. Double-submission is closed by a *required* `idempotencyKey` carried in the mutation variables, so react-query retries, double-clicks, and network retries all reuse one key. Archive and small deletes are immediate-with-undo, so the recoverable path carries zero friction.

**Warning (rung 2).** The typed-count dialog on bulk delete, and the `expectedCount` on the filter target — the server refuses with 409 if the filter now matches a different number than the user read. Control would mean pinning an immutable result-set snapshot server-side; the count check buys most of it for a fraction of the work.

**Left possible on purpose.** Delete really deletes after 30 days, and the UI doesn't gate that — the retention window is the device, and a second dialog there would only train dismissal. Hiding the buttons for unpermitted users is *not* included, because hiding is presentation: the `/api/documents/bulk/*` endpoints must enforce permissions and tenant scoping themselves (that's `poka-yoke:authz`'s half). And the server must cap/chunk `kind: "filter"` operations — the client deliberately never enumerates 40,000 ids, so the bound has to live there.