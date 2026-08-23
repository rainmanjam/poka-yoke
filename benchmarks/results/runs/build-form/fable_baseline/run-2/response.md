Here's the complete implementation. Design decisions baked in: selection is a discriminated union (explicit ids vs "all matching, minus exclusions") so "select all 3,212" never needs 3,212 ids in the browser; Archive and Delete are both soft/reversible and use **undo toasts rather than confirm dialogs**, with one exception — deleting an "all matching" selection above a threshold requires typing the count.

```tsx
// ─────────────────────────────────────────────────────────────────────────────
// types.ts
// ─────────────────────────────────────────────────────────────────────────────
export type DocumentId = string & { readonly __brand: "DocumentId" };

export interface Document {
  id: DocumentId;
  title: string;
  updatedAt: string; // ISO
  ownerName: string;
}

/** The server-side query that produced the current list. Selection is scoped to it. */
export interface DocumentFilter {
  search?: string;
  ownerId?: string;
  updatedAfter?: string;
}

/**
 * Selection is either an explicit set of ids, or "everything the filter matches,
 * except these". The second form is what lets "select all 3,212" work without
 * shipping 3,212 ids to the client or back to the server.
 */
export type Selection =
  | { mode: "ids"; ids: ReadonlySet<DocumentId> }
  | { mode: "all"; filter: DocumentFilter; excluded: ReadonlySet<DocumentId> };

export const EMPTY_SELECTION: Selection = { mode: "ids", ids: new Set() };

/** Wire format. The server resolves "all" against the same filter it paginated with. */
export type SelectionPayload =
  | { mode: "ids"; ids: DocumentId[] }
  | { mode: "all"; filter: DocumentFilter; excludedIds: DocumentId[] };

export function toPayload(s: Selection): SelectionPayload {
  return s.mode === "ids"
    ? { mode: "ids", ids: [...s.ids] }
    : { mode: "all", filter: s.filter, excludedIds: [...s.excluded] };
}

export function selectionCount(s: Selection, totalMatching: number): number {
  return s.mode === "ids" ? s.ids.size : Math.max(0, totalMatching - s.excluded.size);
}

export function isSelected(s: Selection, id: DocumentId): boolean {
  return s.mode === "ids" ? s.ids.has(id) : !s.excluded.has(id);
}

// ─────────────────────────────────────────────────────────────────────────────
// useSelection.ts
// ─────────────────────────────────────────────────────────────────────────────
import { useCallback, useEffect, useMemo, useState } from "react";

export function useSelection(filter: DocumentFilter, pageRows: Document[], totalMatching: number) {
  const [selection, setSelection] = useState<Selection>(EMPTY_SELECTION);

  // A selection is only meaningful against the query that produced it.
  // Changing the filter silently re-targets a pending bulk action, so we clear instead.
  const filterKey = JSON.stringify(filter);
  useEffect(() => setSelection(EMPTY_SELECTION), [filterKey]);

  const toggle = useCallback((id: DocumentId) => {
    setSelection((s) => {
      if (s.mode === "ids") {
        const ids = new Set(s.ids);
        ids.has(id) ? ids.delete(id) : ids.add(id);
        return { mode: "ids", ids };
      }
      const excluded = new Set(s.excluded);
      excluded.has(id) ? excluded.delete(id) : excluded.add(id);
      return { ...s, excluded };
    });
  }, []);

  const pageIds = useMemo(() => pageRows.map((r) => r.id), [pageRows]);
  const pageSelectedCount = pageIds.filter((id) => isSelected(selection, id)).length;
  const pageAllSelected = pageRows.length > 0 && pageSelectedCount === pageRows.length;

  const togglePage = useCallback(() => {
    setSelection((s) => {
      if (s.mode === "all") {
        // In "all" mode the header checkbox un-selects this page (adds to excluded).
        const excluded = new Set(s.excluded);
        pageIds.forEach((id) => excluded.add(id));
        return { ...s, excluded };
      }
      const ids = new Set(s.ids);
      const allOn = pageIds.every((id) => ids.has(id));
      pageIds.forEach((id) => (allOn ? ids.delete(id) : ids.add(id)));
      return { mode: "ids", ids };
    });
  }, [pageIds]);

  const selectAllMatching = useCallback(
    () => setSelection({ mode: "all", filter, excluded: new Set() }),
    [filterKey], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const clear = useCallback(() => setSelection(EMPTY_SELECTION), []);

  return {
    selection,
    count: selectionCount(selection, totalMatching),
    pageAllSelected,
    pageSomeSelected: pageSelectedCount > 0 && !pageAllSelected,
    toggle,
    togglePage,
    selectAllMatching,
    clear,
    isSelected: (id: DocumentId) => isSelected(selection, id),
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// api.ts — mutation calls
// ─────────────────────────────────────────────────────────────────────────────
export interface BulkResult {
  affected: number;
  /** Server-issued handle for reversing this exact batch, valid until `undoExpiresAt`. */
  undoToken: string;
  undoExpiresAt: string;
}

async function post<T>(path: string, body: unknown, idempotencyKey: string): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} failed: ${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const documentsApi = {
  /** Soft-archive. Reversible via undoToken. */
  archive: (selection: Selection, key: string) =>
    post<BulkResult>("/api/documents/bulk/archive", { selection: toPayload(selection) }, key),

  /** Soft-delete → trash (30-day retention). Reversible via undoToken. */
  delete: (selection: Selection, key: string) =>
    post<BulkResult>("/api/documents/bulk/delete", { selection: toPayload(selection) }, key),

  /** Reverses one batch. Idempotent on the server by token. */
  undo: (undoToken: string) =>
    post<{ restored: number }>("/api/documents/bulk/undo", { undoToken }, undoToken),
};

// ─────────────────────────────────────────────────────────────────────────────
// BulkActionsBar.tsx
// ─────────────────────────────────────────────────────────────────────────────
import { useRef, useState } from "react";

type Action = "archive" | "delete";

/** Above this, deleting an "all matching" selection needs the count typed. */
const TYPE_TO_CONFIRM_THRESHOLD = 200;

interface Props {
  selection: Selection;
  count: number;
  totalMatching: number;
  pageSize: number;
  pageAllSelected: boolean;
  onSelectAllMatching: () => void;
  onClear: () => void;
  /** Called after a mutation settles so the table can refetch. */
  onMutated: () => void;
  /** Host-provided toast; returns a dismiss fn. */
  toast: (t: { message: string; action?: { label: string; onClick: () => void }; durationMs: number }) => () => void;
}

export function BulkActionsBar(p: Props) {
  const [pending, setPending] = useState<Action | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  // One key per *attempt*, minted when the user commits, so a retry of the same
  // click dedupes server-side but a fresh click after success is a new operation.
  const keyRef = useRef<string | null>(null);

  if (p.count === 0) return null;

  const isAllMode = p.selection.mode === "all";
  const needsTypedConfirm = isAllMode && p.count >= TYPE_TO_CONFIRM_THRESHOLD;
  const fmt = (n: number) => n.toLocaleString();

  async function run(action: Action) {
    if (pending) return; // structural double-submit guard; button is also disabled
    setPending(action);
    keyRef.current ??= crypto.randomUUID();
    const key = keyRef.current;
    const snapshot = p.selection;
    const n = p.count;
    try {
      const result = await (action === "archive"
        ? documentsApi.archive(snapshot, key)
        : documentsApi.delete(snapshot, key));
      keyRef.current = null;
      p.onClear();
      p.onMutated();
      const verb = action === "archive" ? "Archived" : "Moved to trash";
      const ttl = Math.max(5_000, new Date(result.undoExpiresAt).getTime() - Date.now());
      p.toast({
        message: `${verb} ${fmt(result.affected)} document${result.affected === 1 ? "" : "s"}.`,
        durationMs: Math.min(ttl, 10_000),
        action: {
          label: "Undo",
          onClick: async () => {
            try {
              const r = await documentsApi.undo(result.undoToken);
              p.onMutated();
              p.toast({ message: `Restored ${fmt(r.restored)} document${r.restored === 1 ? "" : "s"}.`, durationMs: 4_000 });
            } catch (e) {
              p.toast({ message: `Couldn't undo: ${(e as Error).message}`, durationMs: 8_000 });
            }
          },
        },
      });
    } catch (e) {
      // Keep the key: a retry of the same selection is the same operation.
      p.toast({ message: `${action === "archive" ? "Archive" : "Delete"} failed — nothing changed. ${(e as Error).message}`, durationMs: 8_000 });
    } finally {
      setPending(null);
      setConfirmingDelete(false);
    }
  }

  return (
    <div
      role="region"
      aria-label="Bulk actions"
      aria-live="polite"
      className="sticky top-0 z-10 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border border-blue-200 bg-blue-50 px-4 py-2 text-sm text-blue-900"
    >
      <span className="font-medium">
        {isAllMode ? `All ${fmt(p.count)} matching documents selected` : `${fmt(p.count)} selected`}
      </span>

      {/* Escalation to "all matching" only appears once the whole page is checked,
          and only when there is more beyond this page. */}
      {!isAllMode && p.pageAllSelected && p.totalMatching > p.pageSize && (
        <button type="button" onClick={p.onSelectAllMatching} className="underline hover:no-underline">
          Select all {fmt(p.totalMatching)} matching
        </button>
      )}

      <button type="button" onClick={p.onClear} className="underline hover:no-underline">
        Clear selection
      </button>

      <div className="ml-auto flex items-center gap-2">
        <button
          type="button"
          disabled={pending !== null}
          onClick={() => run("archive")}
          className="rounded border border-blue-300 bg-white px-3 py-1 font-medium hover:bg-blue-100 disabled:opacity-50"
        >
          {pending === "archive" ? "Archiving…" : `Archive ${fmt(p.count)}`}
        </button>

        {/* Delete is separated from Archive by a divider and styled distinctly — never adjacent-and-identical. */}
        <span aria-hidden className="mx-1 h-5 w-px bg-blue-200" />

        {!confirmingDelete ? (
          <button
            type="button"
            disabled={pending !== null}
            onClick={() => (needsTypedConfirm ? setConfirmingDelete(true) : run("delete"))}
            className="rounded border border-red-300 bg-white px-3 py-1 font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            {pending === "delete" ? "Deleting…" : `Delete ${fmt(p.count)}`}
          </button>
        ) : (
          <TypedConfirm
            count={p.count}
            onConfirm={() => run("delete")}
            onCancel={() => setConfirmingDelete(false)}
            busy={pending === "delete"}
          />
        )}
      </div>
    </div>
  );
}

function TypedConfirm({ count, onConfirm, onCancel, busy }: { count: number; onConfirm: () => void; onCancel: () => void; busy: boolean }) {
  const [typed, setTyped] = useState("");
  const expected = String(count);
  const ok = typed.trim() === expected;
  return (
    <form
      onSubmit={(e) => { e.preventDefault(); if (ok && !busy) onConfirm(); }}
      className="flex items-center gap-2 rounded border border-red-300 bg-red-50 px-2 py-1 text-red-900"
    >
      <label htmlFor="bulk-delete-confirm" className="whitespace-nowrap">
        Move <strong>{count.toLocaleString()}</strong> documents to trash — type <code>{expected}</code> to confirm:
      </label>
      <input
        id="bulk-delete-confirm"
        autoFocus
        inputMode="numeric"
        value={typed}
        onChange={(e) => setTyped(e.target.value)}
        className="w-20 rounded border border-red-300 px-2 py-0.5 font-mono"
      />
      <button type="submit" disabled={!ok || busy} className="rounded bg-red-600 px-3 py-1 font-medium text-white disabled:opacity-40">
        {busy ? "Deleting…" : "Delete"}
      </button>
      <button type="button" onClick={onCancel} className="underline">Cancel</button>
    </form>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// DocumentsTable.tsx — wiring
// ─────────────────────────────────────────────────────────────────────────────
interface TableProps {
  filter: DocumentFilter;
  rows: Document[];          // current page (≤50)
  totalMatching: number;     // from the paginated response
  pageSize?: number;
  refetch: () => void;
  toast: Props["toast"];
}

export function DocumentsTable({ filter, rows, totalMatching, pageSize = 50, refetch, toast }: TableProps) {
  const sel = useSelection(filter, rows, totalMatching);
  const headerRef = useRef<HTMLInputElement>(null);
  useEffect(() => { if (headerRef.current) headerRef.current.indeterminate = sel.pageSomeSelected; }, [sel.pageSomeSelected]);

  return (
    <div className="space-y-2">
      <BulkActionsBar
        selection={sel.selection}
        count={sel.count}
        totalMatching={totalMatching}
        pageSize={pageSize}
        pageAllSelected={sel.pageAllSelected}
        onSelectAllMatching={sel.selectAllMatching}
        onClear={sel.clear}
        onMutated={refetch}
        toast={toast}
      />
      <table className="w-full text-sm">
        <thead className="text-left text-gray-500">
          <tr>
            <th className="w-8 p-2">
              <input ref={headerRef} type="checkbox" aria-label="Select all on this page"
                checked={sel.pageAllSelected} onChange={sel.togglePage} />
            </th>
            <th className="p-2">Title</th><th className="p-2">Owner</th><th className="p-2">Updated</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => {
            const on = sel.isSelected(d.id);
            return (
              <tr key={d.id} className={on ? "bg-blue-50" : "hover:bg-gray-50"}>
                <td className="p-2">
                  <input type="checkbox" aria-label={`Select ${d.title}`} checked={on} onChange={() => sel.toggle(d.id)} />
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

`★ Insight ─────────────────────────────────────`
- **"Select all matching" is a server-side predicate, not a client-side id list.** The `all` mode sends `{filter, excludedIds}`; the server re-runs the same filter inside the mutation. This is what makes thousands of rows tractable, but it also means the action operates on *whatever matches at execution time* — which is why the filter is sent with the selection, not re-read from app state.
- **Undo beats confirm.** Archive and small deletes run immediately with an undo toast; the server issues an `undoToken` per batch, so undo is exact (restores that batch, not "everything deleted recently"). The typed-count confirmation appears only for the one case where blast radius is both large and non-obvious (all-matching ≥ 200).
- **The idempotency key is minted per attempt and kept across failure.** A retry after a network error dedupes server-side; a new click after success gets a fresh key. Disabling the button alone isn't a device — refresh/back/flaky network bypass it.
`─────────────────────────────────────────────────`

**What this makes impossible, and at which rung**
- Acting on a stale selection after a filter change — rung 1 (selection is cleared; `all` mode carries its filter).
- Double-submitting the same batch — rung 1 (disabled + idempotency key).
- Reflexively deleting thousands — rung 1 (type-the-count; cannot be done by click-through).
- Misreading scale — rung 2 (exact count on every button label, not "Delete selected").

**Left possible on purpose**: archive and small deletes have no gate at all. Both are reversible by contract (`undoToken`, trash retention), so a gate would only add friction and train click-through blindness for the one confirm that matters. The server contract this relies on: bulk endpoints must be soft operations, honour `Idempotency-Key`, and resolve `{mode:"all"}` with the *same* filter semantics as list pagination — a mistake-proof bar over a hard-delete endpoint is only half a device.