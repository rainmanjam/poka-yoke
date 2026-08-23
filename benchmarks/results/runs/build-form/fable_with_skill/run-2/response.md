Skill read. Routing: router → `ux` (bulk delete in a UI), plus `lang-typescript.md` and `ux-patterns.md`. The ux skill says: when someone is building, produce the working interface, then a short note on which misuses the shape makes impossible. Here's the code.

## Assumptions

- TanStack Query for mutations; an API exposing `POST /documents/archive`, `/documents/delete`, `/documents/restore`, all accepting a *selection* (explicit IDs **or** a filter snapshot) and returning `{ affected }`.
- Delete is soft-delete with a 30-day trash (the strongest device is backend, so the API is designed for it).
- Filters are an opaque `DocumentFilter` object already used by the list query.

## `documents/selection.ts` — state that cannot be ambiguous

```ts
declare const brand: unique symbol;
type Brand<T, B> = T & { readonly [brand]: B };

export type DocumentId = Brand<string, "DocumentId">;
export const DocumentId = (s: string): DocumentId => s as DocumentId;

export type IdempotencyKey = Brand<string, "IdempotencyKey">;
export const newIdempotencyKey = (): IdempotencyKey =>
  crypto.randomUUID() as IdempotencyKey;

export type DocumentFilter = Readonly<{ q?: string; ownerId?: string; updatedAfter?: string }>;

/**
 * "Select all" on a paginated table has two meanings and they are 50 vs 40,000 rows apart.
 * The two are distinct variants, so every consumer has to say which one it handles.
 *   explicit  — exactly these IDs, chosen by hand on screen
 *   query     — everything matching `filter` (a snapshot), minus `excluded` the user unticked
 */
export type Selection =
  | { kind: "none" }
  | { kind: "explicit"; ids: ReadonlySet<DocumentId> }
  | { kind: "query"; filter: DocumentFilter; total: number; excluded: ReadonlySet<DocumentId> };

export const NONE: Selection = { kind: "none" };

export function selectionCount(s: Selection): number {
  switch (s.kind) {
    case "none":     return 0;
    case "explicit": return s.ids.size;
    case "query":    return s.total - s.excluded.size;
    default:         return assertNever(s);
  }
}

export function isSelected(s: Selection, id: DocumentId): boolean {
  switch (s.kind) {
    case "none":     return false;
    case "explicit": return s.ids.has(id);
    case "query":    return !s.excluded.has(id);
    default:         return assertNever(s);
  }
}

export function toggle(s: Selection, id: DocumentId): Selection {
  switch (s.kind) {
    case "none":
      return { kind: "explicit", ids: new Set([id]) };
    case "explicit": {
      const ids = new Set(s.ids);
      ids.has(id) ? ids.delete(id) : ids.add(id);
      return ids.size === 0 ? NONE : { kind: "explicit", ids };
    }
    case "query": {
      const excluded = new Set(s.excluded);
      excluded.has(id) ? excluded.delete(id) : excluded.add(id);
      return selectionCount({ ...s, excluded }) === 0 ? NONE : { ...s, excluded };
    }
    default:
      return assertNever(s);
  }
}

export function assertNever(x: never): never {
  throw new Error(`Unhandled variant: ${JSON.stringify(x)}`);
}
```

`★ Insight ─────────────────────────────────────`
- A `Set<string>` plus a `selectAll: boolean` flag is the usual shape, and it's the bug: `selectAll=true` with 50 IDs in the set means *either* "these 50" or "all 3,204" depending on who reads it. The discriminated union makes the reader pick, and `assertNever` breaks the build if a fourth variant appears.
- The `query` variant carries a **snapshot** of the filter. If the user changes filters after selecting "all matching", the selection is tied to the old filter — the hook below clears it rather than letting it silently re-target.
`─────────────────────────────────────────────────`

## `documents/api.ts` — mutations that cannot be called wrong

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { Selection, DocumentId, IdempotencyKey } from "./selection";
import { assertNever } from "./selection";

type SelectionPayload =
  | { mode: "ids"; ids: DocumentId[] }
  | { mode: "filter"; filter: DocumentFilterWire; exclude: DocumentId[] };

function toPayload(s: Selection): SelectionPayload {
  switch (s.kind) {
    case "none":     throw new Error("Bulk action on an empty selection"); // UI prevents; this is the self-check
    case "explicit": return { mode: "ids", ids: [...s.ids] };
    case "query":    return { mode: "filter", filter: s.filter, exclude: [...s.excluded] };
    default:         return assertNever(s);
  }
}

type BulkResult = { affected: number; batchId: string };

async function postBulk(
  path: "/documents/archive" | "/documents/delete",
  selection: Selection,
  expected: number,
  key: IdempotencyKey,          // required, not optional — a retry must reuse it
): Promise<BulkResult> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": key },
    body: JSON.stringify({ selection: toPayload(selection), expected }),
  });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  const result = (await res.json()) as BulkResult;
  // Fixed-value check: the server also rejects when its count ≠ `expected`; this is the client half.
  if (result.affected !== expected) {
    throw new Error(`Expected to affect ${expected} documents, server affected ${result.affected}`);
  }
  return result;
}

async function postRestore(batchId: string): Promise<void> {
  const res = await fetch("/documents/restore", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ batchId }),
  });
  if (!res.ok) throw new Error(`restore failed: ${res.status}`);
}

type BulkVars = { selection: Selection; expected: number; key: IdempotencyKey };

export function useArchiveDocuments() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: BulkVars) => postBulk("/documents/archive", v.selection, v.expected, v.key),
    onSettled: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
}

export function useDeleteDocuments() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: BulkVars) => postBulk("/documents/delete", v.selection, v.expected, v.key),
    onSettled: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
}

export function useRestoreBatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: postRestore,
    onSettled: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
}
```

## `documents/useSelection.ts`

```ts
import { useEffect, useState, useCallback } from "react";
import { NONE, toggle, type Selection, type DocumentId, type DocumentFilter } from "./selection";

export function useSelection(filter: DocumentFilter, total: number) {
  const [selection, setSelection] = useState<Selection>(NONE);

  // A selection made under one filter must not be applied under another.
  useEffect(() => { setSelection(NONE); }, [JSON.stringify(filter)]); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    selection,
    toggleRow: useCallback((id: DocumentId) => setSelection((s) => toggle(s, id)), []),
    selectPage: useCallback((ids: DocumentId[]) => setSelection({ kind: "explicit", ids: new Set(ids) }), []),
    selectAllMatching: useCallback(() => setSelection({ kind: "query", filter, total, excluded: new Set() }), [filter, total]),
    clear: useCallback(() => setSelection(NONE), []),
  };
}
```

## `documents/BulkActionsBar.tsx`

```tsx
import { useId, useRef, useState } from "react";
import { selectionCount, newIdempotencyKey, type Selection } from "./selection";
import { useArchiveDocuments, useDeleteDocuments, useRestoreBatch } from "./api";

const TYPE_TO_CONFIRM_THRESHOLD = 100;
const UNDO_WINDOW_MS = 8_000;

type Props = {
  selection: Selection;
  pageSize: number;
  onSelectAllMatching: () => void;
  onClear: () => void;
  onToast: (t: { message: string; undo?: () => void }) => void;
};

export function BulkActionsBar({ selection, pageSize, onSelectAllMatching, onClear, onToast }: Props) {
  const count = selectionCount(selection);
  const archive = useArchiveDocuments();
  const del = useDeleteDocuments();
  const restore = useRestoreBatch();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const busy = archive.isPending || del.isPending;

  if (selection.kind === "none") return null; // the bar does not exist without a selection

  const scope =
    selection.kind === "query"
      ? `all ${count.toLocaleString()} documents matching the current filter`
      : `${count} selected ${count === 1 ? "document" : "documents"}`;

  async function runArchive() {
    const expected = count;
    try {
      const { batchId } = await archive.mutateAsync({ selection, expected, key: newIdempotencyKey() });
      onClear();
      onToast({
        message: `Archived ${expected.toLocaleString()} documents.`,
        undo: () => restore.mutate(batchId),
      });
    } catch (e) {
      onToast({ message: (e as Error).message }); // selection is preserved so the user can retry
    }
  }

  async function runDelete() {
    const expected = count;
    setConfirmingDelete(false);
    try {
      const { batchId } = await del.mutateAsync({ selection, expected, key: newIdempotencyKey() });
      onClear();
      onToast({
        message: `Moved ${expected.toLocaleString()} documents to Trash. They'll be kept for 30 days.`,
        undo: () => restore.mutate(batchId),
      });
    } catch (e) {
      onToast({ message: (e as Error).message });
    }
  }

  return (
    <div
      role="region"
      aria-label="Bulk actions"
      className="sticky top-0 z-10 flex items-center gap-3 rounded-md border border-slate-200 bg-white px-4 py-2 shadow-sm"
    >
      <span className="text-sm font-medium text-slate-900" aria-live="polite">
        {scope}
      </span>

      {selection.kind === "explicit" && count === pageSize && (
        <button type="button" onClick={onSelectAllMatching} className="text-sm text-blue-700 underline">
          Select all matching documents instead
        </button>
      )}

      <button type="button" onClick={onClear} className="text-sm text-slate-600 hover:text-slate-900">
        Clear selection
      </button>

      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          onClick={runArchive}
          disabled={busy}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:opacity-50"
        >
          {archive.isPending ? "Archiving…" : "Archive"}
        </button>

        {/* Spacer: Delete is never adjacent to Archive, and never the primary style */}
        <span aria-hidden className="mx-2 h-5 w-px bg-slate-200" />

        <button
          type="button"
          onClick={() => setConfirmingDelete(true)}
          disabled={busy}
          className="rounded-md px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
        >
          Delete…
        </button>
      </div>

      {confirmingDelete && (
        <DeleteConfirmDialog
          count={count}
          scopeLabel={scope}
          requireTyping={count >= TYPE_TO_CONFIRM_THRESHOLD}
          onCancel={() => setConfirmingDelete(false)}
          onConfirm={runDelete}
        />
      )}
    </div>
  );
}

function DeleteConfirmDialog({
  count, scopeLabel, requireTyping, onCancel, onConfirm,
}: {
  count: number; scopeLabel: string; requireTyping: boolean; onCancel: () => void; onConfirm: () => void;
}) {
  const [typed, setTyped] = useState("");
  const inputId = useId();
  const cancelRef = useRef<HTMLButtonElement>(null);
  const expectedPhrase = String(count);
  const armed = !requireTyping || typed.trim() === expectedPhrase;

  return (
    <div role="dialog" aria-modal="true" aria-labelledby={`${inputId}-title`}
         className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <form
        onSubmit={(e) => { e.preventDefault(); if (armed) onConfirm(); }}
        className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl"
      >
        <h2 id={`${inputId}-title`} className="text-lg font-semibold text-slate-900">
          Move {count.toLocaleString()} {count === 1 ? "document" : "documents"} to Trash?
        </h2>
        <p className="mt-2 text-sm text-slate-700">
          This affects {scopeLabel}. Items stay in Trash for 30 days and can be restored from there.
        </p>

        {requireTyping && (
          <div className="mt-4">
            <label htmlFor={inputId} className="block text-sm text-slate-700">
              Type <strong>{expectedPhrase}</strong> to confirm the number of documents:
            </label>
            <input
              id={inputId}
              inputMode="numeric"
              autoComplete="off"
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <button ref={cancelRef} autoFocus type="button" onClick={onCancel}
                  className="rounded-md border border-slate-300 px-3 py-1.5 text-sm">
            Cancel
          </button>
          <button
            type="submit"
            aria-disabled={!armed}
            onClick={(e) => { if (!armed) e.preventDefault(); }}
            className={`rounded-md px-3 py-1.5 text-sm font-medium text-white ${armed ? "bg-red-600 hover:bg-red-700" : "bg-red-300 cursor-not-allowed"}`}
          >
            Move {count.toLocaleString()} to Trash
          </button>
        </div>
      </form>
    </div>
  );
}
```

## `documents/DocumentsTable.tsx` — wiring

```tsx
import { useQuery } from "@tanstack/react-query";
import { BulkActionsBar } from "./BulkActionsBar";
import { useSelection } from "./useSelection";
import { isSelected, DocumentId, type DocumentFilter } from "./selection";

type Document = { id: string; title: string; updatedAt: string; ownerName: string };
type Page = { items: Document[]; total: number };
const PAGE_SIZE = 50;

export function DocumentsTable({ filter, page, onToast }: {
  filter: DocumentFilter; page: number; onToast: Parameters<typeof BulkActionsBar>[0]["onToast"];
}) {
  const { data } = useQuery<Page>({
    queryKey: ["documents", filter, page],
    queryFn: () => fetch(`/documents?page=${page}&${new URLSearchParams(filter as Record<string, string>)}`).then((r) => r.json()),
  });
  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const sel = useSelection(filter, total);
  const pageIds = items.map((d) => DocumentId(d.id));
  const allOnPage = pageIds.length > 0 && pageIds.every((id) => isSelected(sel.selection, id));

  return (
    <div className="space-y-2">
      <BulkActionsBar
        selection={sel.selection}
        pageSize={pageIds.length}
        onSelectAllMatching={sel.selectAllMatching}
        onClear={sel.clear}
        onToast={onToast}
      />
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-slate-600">
            <th className="w-8 p-2">
              <input type="checkbox" aria-label="Select all on this page" checked={allOnPage}
                     onChange={(e) => (e.target.checked ? sel.selectPage(pageIds) : sel.clear())} />
            </th>
            <th className="p-2">Title</th><th className="p-2">Owner</th><th className="p-2">Updated</th>
          </tr>
        </thead>
        <tbody>
          {items.map((d) => {
            const id = DocumentId(d.id);
            return (
              <tr key={d.id} className={isSelected(sel.selection, id) ? "bg-blue-50" : ""}>
                <td className="p-2">
                  <input type="checkbox" aria-label={`Select ${d.title}`} checked={isSelected(sel.selection, id)}
                         onChange={() => sel.toggleRow(id)} />
                </td>
                <td className="p-2">{d.title}</td>
                <td className="p-2">{d.ownerName}</td>
                <td className="p-2">{new Date(d.updatedAt).toLocaleDateString()}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
```

## Closing note — what this shape makes impossible

| Mistake | Device | Rung |
|---|---|---|
| "Select all" silently meaning 3,204 rows instead of the 50 on screen | `Selection` union: header checkbox only selects the page; "all matching" is a separate explicit click and the bar's label says which one is active | Control |
| Bulk action hitting a different set than the user saw (filter changed after selecting) | `query` variant snapshots the filter; selection resets on filter change | Control |
| Archiving the wrong thing | Immediate + 8s-style Undo toast via `restore(batchId)` — no dialog at all | Control |
| Deleting the wrong thing | Soft-delete to Trash + Undo; above 100 items, type the count (fixed-value check you have to read) | Control for recovery, Warning for gating |
| Server affecting a different count than shown | `expected` sent with the request and checked on the response | Warning (server must also enforce) |
| Double-click / retry re-running the batch | buttons disabled while pending **and** a required `IdempotencyKey` | Control |
| Mis-clicking Delete next to Archive | spatial separator, Delete is text-only red, Cancel has initial focus | Control |
| Calling a mutation with an empty selection | bar doesn't render at `none`; `toPayload` throws as the self-check | Control |

**Left possible on purpose:** Archive has no confirmation at all — it's cheap to reverse, and a dialog there would train click-through on the Delete dialog that matters. Delete under 100 items gets only the named-count dialog, not type-to-confirm, for the same reason. The `expected`-count check is Warning, not Control, because only the server can make it atomic — it should reject (not partially apply) when its count ≠ `expected`, and the idempotency key should be a unique index on the backend. Hiding the bar is presentation only; the endpoints must enforce authorization themselves (see the `authz` mode).