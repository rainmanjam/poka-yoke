Using **poka-yoke:poka-yoke** → routed to **poka-yoke:ux** (building a bulk destructive action), with `references/ux-patterns.md`, `hazard-catalog.md` (F2, F7, M2, C8), and `lang-typescript.md`.

The dangerous property here is the one that reference names outright: **selection scale is invisible**. "Select all" that silently means *all 4,312 matching* rather than *the 50 on screen* is the trap, and it's a data-model problem before it's a UI problem — so the selection is a discriminated union, not a `Set<string>` plus a boolean.

Assumptions: React 19, TanStack Query v5, zod, Tailwind, `strict: true`. Archive is reversible; Delete is a **soft delete into Trash with 30-day retention** (backend change, and it's the device that does the most work here).

---

## 1. `documents/types.ts` — branded ids, query scope, wire schemas

```ts
import { z } from "zod";

declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type DocumentId = Brand<string, "DocumentId">;
export const DocumentId = (s: string): DocumentId => s as DocumentId;

/** M2: minted per user *intent*, not per request, so a retry reuses it. */
export type IdempotencyKey = Brand<string, "IdempotencyKey">;
export const IdempotencyKey = {
  create: (): IdempotencyKey => crypto.randomUUID() as IdempotencyKey,
};

export type UndoToken = Brand<string, "UndoToken">;

export const DocumentSchema = z.object({
  id: z.string().transform(DocumentId),
  title: z.string(),
  updatedAt: z.string().datetime(),
  ownerName: z.string(),
});
export type Document = z.infer<typeof DocumentSchema>;

export const DocumentPageSchema = z.object({
  items: z.array(DocumentSchema),
  /** Total matching the *filter*, not the page. Drives every count the user sees. */
  total: z.number().int().nonnegative(),
  page: z.number().int().positive(),
  pageSize: z.number().int().positive(),
});
export type DocumentPage = z.infer<typeof DocumentPageSchema>;

export type DocumentQuery = {
  readonly search: string;
  readonly ownerId: string | null;
  readonly updatedWithin: "any" | "7d" | "30d";
  readonly sort: "updatedAt" | "title";
  readonly page: number;
};

/**
 * Identity of the *matching set*. Deliberately excludes `sort` and `page`:
 * paging or re-sorting does not change which documents match, so it must not
 * drop a selection — but changing a filter does, and a stale "all matching"
 * selection would then delete a different set than the user chose.
 */
export const scopeKeyOf = (q: DocumentQuery): string =>
  JSON.stringify([q.search, q.ownerId, q.updatedWithin]);
```

## 2. `documents/selection.ts` — the union, and the reducer that is its only constructor

```ts
import type { DocumentId, DocumentQuery } from "./types";
import { scopeKeyOf } from "./types";

/**
 * C8: three real states, not `Set<id> + selectAll: boolean` (which admits
 * "select-all AND an empty set" and forces every consumer to guess).
 * `allMatching` is a *description* of a set the client has never seen.
 */
export type Selection =
  | { readonly mode: "none" }
  | { readonly mode: "include"; readonly ids: ReadonlySet<DocumentId> }
  | {
      readonly mode: "allMatching";
      readonly excluded: ReadonlySet<DocumentId>;
      readonly matchTotal: number;
    };

export type ActionableSelection = Exclude<Selection, { mode: "none" }>;

export type SelectionState = {
  /** Scope this selection was made under. Mismatch = the selection is void. */
  readonly scope: string;
  readonly selection: Selection;
};

export type SelectionAction =
  | { type: "rows/set"; ids: readonly DocumentId[]; selected: boolean }
  | { type: "allMatching/select"; matchTotal: number }
  | { type: "clear" };

export const emptySelectionState = (query: DocumentQuery): SelectionState => ({
  scope: scopeKeyOf(query),
  selection: { mode: "none" },
});

const NONE: Selection = { mode: "none" };

/** Normalizes empty sets back to `none`, so "0 selected" has one spelling. */
const normalize = (s: Selection): Selection => {
  if (s.mode === "include" && s.ids.size === 0) return NONE;
  if (s.mode === "allMatching" && s.excluded.size >= s.matchTotal) return NONE;
  return s;
};

const withIds = (
  base: ReadonlySet<DocumentId>,
  ids: readonly DocumentId[],
  present: boolean,
): ReadonlySet<DocumentId> => {
  const next = new Set(base);
  for (const id of ids) (present ? next.add(id) : next.delete(id));
  return next;
};

export function selectionReducer(
  state: SelectionState,
  action: SelectionAction & { scope: string },
): SelectionState {
  // Filter changed under us: discard synchronously, in the same render pass
  // that the action arrives. An effect-based reset leaves a window in which a
  // click can act on the previous filter's set.
  const base: SelectionState =
    action.scope === state.scope ? state : { scope: action.scope, selection: NONE };

  const { selection } = base;
  switch (action.type) {
    case "clear":
      return { ...base, selection: NONE };

    case "allMatching/select":
      return {
        ...base,
        selection: normalize({
          mode: "allMatching",
          excluded: new Set(),
          matchTotal: action.matchTotal,
        }),
      };

    case "rows/set": {
      if (selection.mode === "allMatching") {
        // Un-ticking a row inside "all matching" is an exclusion, not a new set.
        return {
          ...base,
          selection: normalize({
            ...selection,
            excluded: withIds(selection.excluded, action.ids, !action.selected),
          }),
        };
      }
      const current = selection.mode === "include" ? selection.ids : new Set<DocumentId>();
      return {
        ...base,
        selection: normalize({
          mode: "include",
          ids: withIds(current, action.ids, action.selected),
        }),
      };
    }
  }
}

export const selectionCount = (s: Selection): number => {
  switch (s.mode) {
    case "none":
      return 0;
    case "include":
      return s.ids.size;
    case "allMatching":
      return Math.max(0, s.matchTotal - s.excluded.size);
  }
};

export const isRowSelected = (s: Selection, id: DocumentId): boolean => {
  switch (s.mode) {
    case "none":
      return false;
    case "include":
      return s.ids.has(id);
    case "allMatching":
      return !s.excluded.has(id);
  }
};

/** Reads the selection only if it still belongs to the query on screen. */
export const selectionFor = (state: SelectionState, query: DocumentQuery): Selection =>
  state.scope === scopeKeyOf(query) ? state.selection : NONE;
```

★ Insight ─────────────────────────────────────
`allMatching` deliberately stores *no ids*. The client cannot enumerate 4,312 rows it never fetched, so any design that tries (fetch-all-ids on "select all") silently caps at whatever it managed to load and deletes a subset. Describing the set — filter plus exclusions — is the only representation that stays true at any scale.
`scope` on the reducer state is the cheap half of that: an "all matching" selection is a *promise about a filter*, so it has to die the instant the filter does, synchronously rather than in an effect.
─────────────────────────────────────────────────

## 3. `documents/api.ts` — mutations that can't be fired unbounded or twice

```ts
import { z } from "zod";
import {
  DocumentId,
  type DocumentQuery,
  type IdempotencyKey,
  type UndoToken,
} from "./types";
import type { ActionableSelection } from "./selection";

/** F2: a bulk mutation is addressed either by an explicit id list or by a
 *  filter + exclusions. There is no third shape, and no empty-predicate shape. */
export type BulkTarget =
  | { readonly kind: "ids"; readonly ids: readonly DocumentId[] }
  | {
      readonly kind: "query";
      readonly query: DocumentQuery;
      readonly excludedIds: readonly DocumentId[];
      /** Blast-radius cap: server aborts if the live count exceeds this. */
      readonly expectedCount: number;
    };

export class EmptyBulkTargetError extends Error {}

/** Only constructor for a target — takes a selection that cannot be `none`. */
export function toBulkTarget(
  selection: ActionableSelection,
  query: DocumentQuery,
  expectedCount: number,
): BulkTarget {
  if (expectedCount <= 0) throw new EmptyBulkTargetError("refusing a 0-document bulk action");
  if (selection.mode === "include") {
    return { kind: "ids", ids: [...selection.ids] };
  }
  return {
    kind: "query",
    query,
    excludedIds: [...selection.excluded],
    expectedCount,
  };
}

export const SkippedSchema = z.object({
  id: z.string().transform(DocumentId),
  reason: z.enum(["forbidden", "not_found", "already_applied"]),
});

export const BulkReceiptSchema = z.object({
  batchId: z.string(),
  affected: z.number().int().nonnegative(),
  skipped: z.array(SkippedSchema),
  /** Null when nothing was affected, so "Undo" is never offered as a no-op. */
  undoToken: z.string().nullable().transform((t) => t as UndoToken | null),
  undoExpiresAt: z.string().datetime(),
});
export type BulkReceipt = z.infer<typeof BulkReceiptSchema>;

/**
 * M2 — the key is a required field, not an option. Server contract:
 *   • unique index on (actor_id, idempotency_key), reserved in the same
 *     transaction as the effect;
 *   • key bound to a hash of the payload — same key + different target is a
 *     409, not a silent no-op;
 *   • replay returns the *stored receipt*, so a retry learns what the first
 *     attempt actually did;
 *   • F7 — hard server cap (MAX_BULK = 10_000) independent of what we send;
 *   • kind:"query" — server aborts with 409 count_mismatch if the live count
 *     exceeds expectedCount (someone else's rows must not join the batch).
 */
export type BulkMutationInput = {
  readonly target: BulkTarget;
  readonly idempotencyKey: IdempotencyKey;
  readonly signal?: AbortSignal;
};

async function post<T extends z.ZodTypeAny>(
  path: string,
  body: unknown,
  key: IdempotencyKey,
  schema: T,
  signal?: AbortSignal,
): Promise<z.infer<T>> {
  const res = await fetch(path, {
    method: "POST",
    signal,
    headers: { "content-type": "application/json", "idempotency-key": key },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${path} failed: ${res.status} ${detail}`);
  }
  // C7: parse at the boundary. An unchecked `affected` drives a count we show
  // the user, and a wrong count here is worse than an error.
  return schema.parse(await res.json());
}

export const archiveDocuments = ({ target, idempotencyKey, signal }: BulkMutationInput) =>
  post("/api/documents/bulk/archive", { target }, idempotencyKey, BulkReceiptSchema, signal);

/** Soft delete → Trash, 30-day retention. The real device: nothing is lost. */
export const trashDocuments = ({ target, idempotencyKey, signal }: BulkMutationInput) =>
  post("/api/documents/bulk/trash", { target }, idempotencyKey, BulkReceiptSchema, signal);

/** The token identifies one batch and is single-use, so undo is idempotent by construction. */
export const undoBulk = (undoToken: UndoToken) =>
  post("/api/documents/bulk/undo", { undoToken }, undoToken as unknown as IdempotencyKey, BulkReceiptSchema);
```

## 4. `documents/useBulkDocumentActions.ts` — intent-scoped keys, undo toasts

```ts
import { useCallback, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  archiveDocuments,
  trashDocuments,
  undoBulk,
  toBulkTarget,
  type BulkReceipt,
} from "./api";
import { IdempotencyKey, type DocumentQuery } from "./types";
import { type ActionableSelection } from "./selection";
import { useToasts } from "../ui/toasts";

export type BulkVerb = "archive" | "trash";

/**
 * One key per user intent. A double-click, a StrictMode double-invoke, or a
 * retry after a network error all reuse it; only a settled intent mints a new
 * one. The disabled button is the visible half of this device, the key is the
 * half that survives a refresh mid-flight.
 */
function useIntentKey() {
  const ref = useRef<IdempotencyKey | null>(null);
  const begin = useCallback(() => (ref.current ??= IdempotencyKey.create()), []);
  const settle = useCallback(() => {
    ref.current = null;
  }, []);
  return { begin, settle };
}

const nf = new Intl.NumberFormat();

const describe = (verb: BulkVerb, r: BulkReceipt): string => {
  const noun = r.affected === 1 ? "document" : "documents";
  const done = verb === "archive" ? "Archived" : "Moved to Trash:";
  const head = `${done} ${nf.format(r.affected)} ${noun}`;
  return r.skipped.length > 0 ? `${head} · ${nf.format(r.skipped.length)} skipped` : head;
};

export function useBulkDocumentActions(query: DocumentQuery, onSettled: () => void) {
  const qc = useQueryClient();
  const toasts = useToasts();
  const archiveIntent = useIntentKey();
  const trashIntent = useIntentKey();

  const invalidate = () => qc.invalidateQueries({ queryKey: ["documents"] });

  const undo = useMutation({
    mutationFn: undoBulk,
    onSuccess: (r) => {
      invalidate();
      toasts.show({ text: `Restored ${nf.format(r.affected)} documents.` });
    },
    onError: (e: Error) => toasts.show({ tone: "error", text: `Undo failed: ${e.message}` }),
  });

  const run = (verb: BulkVerb, intent: ReturnType<typeof useIntentKey>) =>
    useMutation({
      mutationFn: (vars: { selection: ActionableSelection; count: number }) =>
        (verb === "archive" ? archiveDocuments : trashDocuments)({
          target: toBulkTarget(vars.selection, query, vars.count),
          idempotencyKey: intent.begin(),
        }),
      onSuccess: (receipt, vars) => {
        intent.settle();
        onSettled();
        invalidate();
        toasts.show({
          text: describe(verb, receipt),
          // Grace-period undo: the happy path pays no friction at all.
          action:
            receipt.undoToken && receipt.affected > 0
              ? { label: "Undo", onClick: () => undo.mutate(receipt.undoToken!) }
              : undefined,
          durationMs: 10_000,
        });
        if (receipt.affected !== vars.count) {
          toasts.show({
            tone: "warning",
            text: `Expected ${nf.format(vars.count)}, applied ${nf.format(receipt.affected)}. The list may have changed.`,
          });
        }
      },
      // Intent NOT settled on error: a retry reuses the same key.
      onError: (e: Error) =>
        toasts.show({ tone: "error", text: `Nothing was changed — ${e.message}`, action: undefined }),
    });

  return {
    archive: run("archive", archiveIntent),
    trash: run("trash", trashIntent),
    cancelTrashIntent: trashIntent.settle,
  };
}
```

## 5. `documents/BulkActionsBar.tsx`

```tsx
import { useEffect, useRef, useState } from "react";
import type { ActionableSelection } from "./selection";
import { selectionCount } from "./selection";

const nf = new Intl.NumberFormat();

type Props = {
  selection: ActionableSelection;
  /** Rows on the current page, for the "select all N matching" escalation. */
  pageSelectedCount: number;
  matchTotal: number;
  busy: boolean;
  onSelectAllMatching: () => void;
  onClear: () => void;
  onArchive: () => void;
  onRequestTrash: () => void;
};

export function BulkActionsBar({
  selection,
  pageSelectedCount,
  matchTotal,
  busy,
  onSelectAllMatching,
  onClear,
  onArchive,
  onRequestTrash,
}: Props) {
  const count = selectionCount(selection);
  const barRef = useRef<HTMLDivElement>(null);

  // The trap, made explicit: offer the escalation only when the whole page is
  // ticked, label it with the real number, and never perform it implicitly.
  const canEscalate =
    selection.mode === "include" &&
    pageSelectedCount > 0 &&
    pageSelectedCount === count &&
    matchTotal > count;

  return (
    <div
      ref={barRef}
      role="region"
      aria-label="Bulk actions"
      className="sticky bottom-0 z-20 border-t border-slate-200 bg-white/95 px-4 py-3 shadow-[0_-4px_16px_rgba(15,23,42,0.08)] backdrop-blur dark:border-slate-700 dark:bg-slate-900/95"
    >
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2">
        {/* Scale, stated before any action — fixed-value inspection. */}
        <p className="text-sm font-medium text-slate-900 dark:text-slate-100" aria-live="polite">
          {nf.format(count)} {count === 1 ? "document" : "documents"} selected
          {selection.mode === "allMatching" && (
            <span className="ml-1 font-normal text-slate-500 dark:text-slate-400">
              (everything matching your filters)
            </span>
          )}
        </p>

        {canEscalate && (
          <button
            type="button"
            onClick={onSelectAllMatching}
            className="rounded text-sm font-medium text-sky-700 underline underline-offset-2 hover:text-sky-900 dark:text-sky-400"
          >
            Select all {nf.format(matchTotal)} matching documents
          </button>
        )}

        <button
          type="button"
          onClick={onClear}
          className="rounded text-sm text-slate-500 underline underline-offset-2 hover:text-slate-800 dark:text-slate-400"
        >
          Clear selection
        </button>

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={onArchive}
            disabled={busy}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900"
          >
            {busy ? "Working…" : "Archive"}
          </button>

          {/* Destructive action separated, de-emphasised, never autofocused,
              and never the primary button. */}
          <span aria-hidden className="mx-1 h-6 w-px bg-slate-200 dark:bg-slate-700" />
          <button
            type="button"
            onClick={onRequestTrash}
            disabled={busy}
            className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-500/60 dark:text-red-400 dark:hover:bg-red-500/10"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}
```

## 6. `documents/ConfirmBulkTrashDialog.tsx`

```tsx
import { useEffect, useId, useRef, useState } from "react";

const nf = new Intl.NumberFormat();

/** Below this, Delete runs immediately with an Undo toast — no dialog at all. */
export const TRASH_DIALOG_THRESHOLD = 25;
/** Above this (or for "all matching"), the count must be typed. */
export const TYPE_TO_CONFIRM_THRESHOLD = 100;

type Props = {
  count: number;
  scopeIsWholeFilter: boolean;
  sampleTitles: readonly string[];
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ConfirmBulkTrashDialog({
  count,
  scopeIsWholeFilter,
  sampleTitles,
  busy,
  onCancel,
  onConfirm,
}: Props) {
  const [typed, setTyped] = useState("");
  const cancelRef = useRef<HTMLButtonElement>(null);
  const inputId = useId();
  const reasonId = useId();

  const mustType = scopeIsWholeFilter || count >= TYPE_TO_CONFIRM_THRESHOLD;
  const expected = String(count);
  const typedOk = !mustType || typed.replace(/[\s,]/g, "") === expected;

  // Safe default focus: Cancel, never the destructive button.
  useEffect(() => cancelRef.current?.focus(), []);

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-slate-900/40 p-4"
      onKeyDown={(e) => e.key === "Escape" && !busy && onCancel()}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="bulk-trash-title"
        aria-describedby="bulk-trash-body"
        className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl dark:bg-slate-900"
      >
        {/* Names the object class, states the scale, states reversibility honestly. */}
        <h2
          id="bulk-trash-title"
          className="text-base font-semibold text-slate-900 dark:text-slate-100"
        >
          Move {nf.format(count)} {count === 1 ? "document" : "documents"} to Trash?
        </h2>

        <div id="bulk-trash-body" className="mt-2 space-y-2 text-sm text-slate-600 dark:text-slate-300">
          <p>
            They will be recoverable from Trash for 30 days, then deleted permanently.
            Shared links stop working immediately.
          </p>
          {sampleTitles.length > 0 && (
            <p className="text-slate-500 dark:text-slate-400">
              Including {sampleTitles.map((t) => `“${t}”`).join(", ")}
              {count > sampleTitles.length && ` and ${nf.format(count - sampleTitles.length)} more`}.
            </p>
          )}
          {scopeIsWholeFilter && (
            <p className="rounded bg-amber-50 px-2 py-1.5 text-amber-900 dark:bg-amber-500/10 dark:text-amber-300">
              This applies to every document matching your current filters — not just the
              50 shown on this page.
            </p>
          )}
        </div>

        {mustType && (
          <div className="mt-4">
            <label htmlFor={inputId} className="block text-sm text-slate-700 dark:text-slate-200">
              Type <span className="font-mono font-semibold">{expected}</span> to confirm
            </label>
            <input
              id={inputId}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              inputMode="numeric"
              autoComplete="off"
              className="mt-1 w-32 rounded border border-slate-300 px-2 py-1 font-mono text-sm dark:border-slate-600 dark:bg-slate-800"
            />
          </div>
        )}

        <div className="mt-5 flex items-center justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white dark:bg-slate-100 dark:text-slate-900"
          >
            Cancel
          </button>
          {/* aria-disabled, not disabled: the button stays focusable so the
              unmet requirement is announced on the control itself. */}
          <button
            type="button"
            aria-disabled={!typedOk || busy}
            aria-describedby={typedOk ? undefined : reasonId}
            onClick={() => typedOk && !busy && onConfirm()}
            className={`rounded-md border px-3 py-1.5 text-sm font-medium ${
              typedOk && !busy
                ? "border-red-600 bg-red-600 text-white hover:bg-red-700"
                : "cursor-not-allowed border-red-200 bg-red-100 text-red-400 dark:border-red-900 dark:bg-red-950 dark:text-red-700"
            }`}
          >
            {busy ? "Moving…" : `Move ${nf.format(count)} to Trash`}
          </button>
          <p id={reasonId} className="sr-only">
            Type the number {expected} to enable this button.
          </p>
        </div>
      </div>
    </div>
  );
}
```

## 7. `documents/DocumentsTable.tsx` — wiring

```tsx
import { useCallback, useMemo, useReducer, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  emptySelectionState,
  isRowSelected,
  selectionCount,
  selectionFor,
  selectionReducer,
  type ActionableSelection,
} from "./selection";
import { DocumentPageSchema, scopeKeyOf, type Document, type DocumentId, type DocumentQuery } from "./types";
import { BulkActionsBar } from "./BulkActionsBar";
import { ConfirmBulkTrashDialog, TRASH_DIALOG_THRESHOLD } from "./ConfirmBulkTrashDialog";
import { useBulkDocumentActions } from "./useBulkDocumentActions";

const fetchDocuments = async (q: DocumentQuery) => {
  const params = new URLSearchParams({
    search: q.search,
    updatedWithin: q.updatedWithin,
    sort: q.sort,
    page: String(q.page),
    pageSize: "50",
    ...(q.ownerId ? { ownerId: q.ownerId } : {}),
  });
  const res = await fetch(`/api/documents?${params}`);
  if (!res.ok) throw new Error(`Failed to load documents (${res.status})`);
  return DocumentPageSchema.parse(await res.json());
};

export function DocumentsTable({ query }: { query: DocumentQuery }) {
  const scope = scopeKeyOf(query);
  const [state, rawDispatch] = useReducer(selectionReducer, query, emptySelectionState);
  const dispatch = useCallback(
    (a: Parameters<typeof selectionReducer>[1] extends infer _ ? any : never) =>
      rawDispatch({ ...a, scope }),
    [scope],
  );

  const { data, isPending, error } = useQuery({
    queryKey: ["documents", query],
    queryFn: () => fetchDocuments(query),
    placeholderData: (prev) => prev,
  });

  const selection = selectionFor(state, query);
  const count = selectionCount(selection);
  const [confirming, setConfirming] = useState(false);
  const lastIndexRef = useRef<number | null>(null);

  const clear = useCallback(() => dispatch({ type: "clear" }), [dispatch]);
  const { archive, trash, cancelTrashIntent } = useBulkDocumentActions(query, clear);
  const busy = archive.isPending || trash.isPending;

  const items = data?.items ?? [];
  const pageIds = useMemo(() => items.map((d) => d.id), [items]);
  const pageSelectedCount = pageIds.filter((id) => isRowSelected(selection, id)).length;

  const headerRef = useRef<HTMLInputElement>(null);
  if (headerRef.current) {
    headerRef.current.indeterminate =
      pageSelectedCount > 0 && pageSelectedCount < pageIds.length;
  }

  const toggleRow = (index: number, id: DocumentId, selected: boolean, shift: boolean) => {
    const from = shift && lastIndexRef.current !== null ? lastIndexRef.current : index;
    const [lo, hi] = from <= index ? [from, index] : [index, from];
    lastIndexRef.current = index;
    dispatch({ type: "rows/set", ids: pageIds.slice(lo, hi + 1), selected });
  };

  const runTrash = () => {
    setConfirming(false);
    trash.mutate({ selection: selection as ActionableSelection, count });
  };

  if (error) return <p className="p-4 text-sm text-red-700">{(error as Error).message}</p>;

  return (
    <div
      className="flex h-full flex-col"
      onKeyDown={(e) => {
        if (e.key === "Escape" && !confirming && count > 0) clear();
      }}
    >
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 bg-slate-50 text-left dark:bg-slate-800">
          <tr>
            <th scope="col" className="w-10 px-3 py-2">
              <input
                ref={headerRef}
                type="checkbox"
                // Page-scoped only. "All matching" is a separate, labelled act.
                aria-label={`Select all ${pageIds.length} documents on this page`}
                checked={pageIds.length > 0 && pageSelectedCount === pageIds.length}
                onChange={(e) => dispatch({ type: "rows/set", ids: pageIds, selected: e.target.checked })}
                className="h-4 w-4 rounded border-slate-300"
              />
            </th>
            <th scope="col" className="px-3 py-2 font-medium">Title</th>
            <th scope="col" className="px-3 py-2 font-medium">Owner</th>
            <th scope="col" className="px-3 py-2 font-medium">Updated</th>
          </tr>
        </thead>
        <tbody>
          {isPending && !data ? (
            <tr><td colSpan={4} className="px-3 py-8 text-center text-slate-500">Loading…</td></tr>
          ) : items.length === 0 ? (
            <tr><td colSpan={4} className="px-3 py-8 text-center text-slate-500">No documents match these filters.</td></tr>
          ) : (
            items.map((doc: Document, i) => {
              const selected = isRowSelected(selection, doc.id);
              return (
                <tr
                  key={doc.id}
                  className={`border-t border-slate-100 dark:border-slate-800 ${selected ? "bg-sky-50 dark:bg-sky-500/10" : ""}`}
                >
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selected}
                      aria-label={`Select ${doc.title}`}
                      onClick={(e) => toggleRow(i, doc.id, !selected, (e as React.MouseEvent).shiftKey)}
                      onChange={() => {}}
                      className="h-4 w-4 rounded border-slate-300"
                    />
                  </td>
                  <td className="px-3 py-2 text-slate-900 dark:text-slate-100">{doc.title}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-400">{doc.ownerName}</td>
                  <td className="px-3 py-2 text-slate-600 dark:text-slate-400">
                    {new Date(doc.updatedAt).toLocaleDateString()}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>

      {selection.mode !== "none" && (
        <BulkActionsBar
          selection={selection}
          pageSelectedCount={pageSelectedCount}
          matchTotal={data?.total ?? 0}
          busy={busy}
          onSelectAllMatching={() =>
            dispatch({ type: "allMatching/select", matchTotal: data?.total ?? 0 })
          }
          onClear={clear}
          // Reversible → runs immediately, undo lives in the toast.
          onArchive={() => archive.mutate({ selection, count })}
          onRequestTrash={() =>
            count <= TRASH_DIALOG_THRESHOLD && selection.mode === "include"
              ? trash.mutate({ selection, count })
              : setConfirming(true)
          }
        />
      )}

      {confirming && selection.mode !== "none" && (
        <ConfirmBulkTrashDialog
          count={count}
          scopeIsWholeFilter={selection.mode === "allMatching"}
          sampleTitles={items.filter((d) => isRowSelected(selection, d.id)).slice(0, 3).map((d) => d.title)}
          busy={trash.isPending}
          onCancel={() => {
            setConfirming(false);
            cancelTrashIntent();
          }}
          onConfirm={runTrash}
        />
      )}
    </div>
  );
}
```

## 8. `ui/toasts.tsx` — minimal undo-capable toaster

```tsx
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

type Toast = {
  id: string;
  text: string;
  tone?: "info" | "warning" | "error";
  action?: { label: string; onClick: () => void };
  durationMs?: number;
};

const Ctx = createContext<{ show: (t: Omit<Toast, "id">) => void } | null>(null);

export const useToasts = () => {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToasts must be used inside <ToastProvider>");
  return ctx;
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<readonly Toast[]>([]);

  const show = useCallback((t: Omit<Toast, "id">) => {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { ...t, id }]);
    // Errors persist until dismissed; success/undo toasts expire.
    if (t.tone !== "error") {
      setTimeout(() => setToasts((p) => p.filter((x) => x.id !== id)), t.durationMs ?? 6000);
    }
  }, []);

  const value = useMemo(() => ({ show }), [show]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <div role="status" aria-live="polite" className="fixed bottom-20 left-1/2 z-50 -translate-x-1/2 space-y-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`flex items-center gap-3 rounded-md px-4 py-2 text-sm shadow-lg ${
              t.tone === "error"
                ? "bg-red-700 text-white"
                : t.tone === "warning"
                  ? "bg-amber-600 text-white"
                  : "bg-slate-900 text-white"
            }`}
          >
            <span>{t.text}</span>
            {t.action && (
              <button
                type="button"
                onClick={() => {
                  t.action!.onClick();
                  setToasts((p) => p.filter((x) => x.id !== t.id));
                }}
                className="font-semibold underline underline-offset-2"
              >
                {t.action.label}
              </button>
            )}
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => setToasts((p) => p.filter((x) => x.id !== t.id))}
              className="ml-1 opacity-60 hover:opacity-100"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
```

---

## What this makes impossible, and what it leaves open

| Mistake | Device | Rung |
|---|---|---|
| "Select all" silently meaning 4,312 instead of 50 | Header checkbox is page-scoped by type; `allMatching` is a separate labelled act stating the number | **Control** |
| Acting on a selection made under a different filter | `scope` on the reducer state; mismatched actions reset synchronously, and `selectionFor` refuses to read a stale selection during render | **Control** |
| Bulk action with an empty predicate | `toBulkTarget` takes `ActionableSelection` (no `none` variant) and throws below 1; the bar doesn't render at 0 | **Control** at the type, **Warning** at the throw (the reducer normalizes `include:{}` → `none`, but TypeScript can't prove a set is non-empty) |
| Double-click / refresh mid-submit charging twice | Idempotency key required in `BulkMutationInput`, minted per *intent* and reused on retry, backed by a unique index | **Control** |
| Deleting the wrong thing | Soft delete to Trash + 30-day retention + Undo toast — the mistake has no permanent consequence | **Control** |
| Not knowing the blast radius | Count stated in the bar, in the dialog title, and on the confirm button; `expectedCount` sent so the server aborts if the live set grew | **Control** server-side, **Warning** in the UI |
| Reflexive confirm on a huge batch | Type-the-count above 100 or for whole-filter scope | **Warning** |
| Mis-click Delete instead of Archive | Spatially separated, danger-outline not primary, cancel takes default focus in the dialog | **Warning** |

**Left possible on purpose.** Archive gets no dialog at all — it's reversible, and a confirm on every archive is what trains people to click through the one that matters. Delete under 25 explicitly-ticked rows also skips the dialog and relies on the Undo toast; the dialog is reserved for the case where the user cannot see what they selected.

**The two things that are not done in this code.** Hiding the buttons is presentation — the `/bulk/*` endpoints must enforce per-document permission themselves and report refusals in `skipped`, or the whole bar is a suggestion the API ignores. And the `MAX_BULK` cap and the `count_mismatch` abort are contracts asserted in comments here; they are only devices once they exist server-side with a test that shows them rejecting.