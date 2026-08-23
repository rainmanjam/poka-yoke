Assumptions: the parent already fetches each 50-row page and supplies a server-issued `scope.id` that uniquely represents the current filters/search. The bulk endpoints enforce authorization, scope validity, soft-archive undo, and idempotency server-side.

```tsx
import { useEffect, useRef, useState } from "react";

export type Document = {
  id: string;
  title: string;
  updatedAt: string;
  ownerName: string;
};

export type DocumentPage = {
  items: Document[]; // Maximum 50 rows
  pageNumber: number;
};

export type DocumentSelectionScope = {
  /**
   * Opaque, server-issued snapshot/query ID. Generate a new value whenever
   * filters, search, or tenant context changes.
   */
  id: string;
  total: number;
};

type Selection =
  | { kind: "ids"; ids: Set<string> }
  | { kind: "allMatching"; scopeId: string; excludedIds: Set<string> };

type BulkSelectionPayload =
  | { mode: "ids"; ids: string[] }
  | { mode: "all_matching"; scopeId: string; excludedIds: string[] };

type BulkMutationResult = {
  operationId: string;
  affectedCount: number;
  undoableUntil?: string;
};

type MutationKind = "idle" | "archiving" | "deleting" | "undoing";

type DocumentsTableProps = {
  page: DocumentPage;
  scope: DocumentSelectionScope;
  onReload?: () => void | Promise<void>;
};

const emptySelection = (): Selection => ({ kind: "ids", ids: new Set() });

function documentLabel(count: number) {
  return `${count.toLocaleString()} document${count === 1 ? "" : "s"}`;
}

function isSelected(selection: Selection, documentId: string) {
  return selection.kind === "ids"
    ? selection.ids.has(documentId)
    : !selection.excludedIds.has(documentId);
}

function selectionCount(selection: Selection, scope: DocumentSelectionScope) {
  if (selection.kind === "ids") return selection.ids.size;

  // A stale all-matching selection must never be usable against new filters.
  if (selection.scopeId !== scope.id) return 0;

  return Math.max(0, scope.total - selection.excludedIds.size);
}

function selectionPayload(
  selection: Selection,
  scope: DocumentSelectionScope,
): BulkSelectionPayload | null {
  if (selection.kind === "ids") {
    return selection.ids.size > 0
      ? { mode: "ids", ids: [...selection.ids] }
      : null;
  }

  if (selection.scopeId !== scope.id) return null;

  return {
    mode: "all_matching",
    scopeId: selection.scopeId,
    excludedIds: [...selection.excludedIds],
  };
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const payload: unknown = await response.json().catch(() => null);
    const message =
      typeof payload === "object" &&
      payload !== null &&
      "message" in payload &&
      typeof payload.message === "string"
        ? payload.message
        : `Request failed (${response.status})`;

    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

function PageSelectionCheckbox({
  checked,
  indeterminate,
  disabled,
  onChange,
}: {
  checked: boolean;
  indeterminate: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <input
      ref={ref}
      type="checkbox"
      checked={checked}
      disabled={disabled}
      aria-label="Select all documents on this page"
      onChange={(event) => onChange(event.currentTarget.checked)}
      className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 disabled:cursor-not-allowed"
    />
  );
}

function DeleteDialog({
  count,
  pending,
  error,
  onCancel,
  onConfirm,
}: {
  count: number;
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const phrase = `DELETE ${count.toLocaleString()} DOCUMENTS`;
  const [typedPhrase, setTypedPhrase] = useState("");

  useEffect(() => {
    setTypedPhrase("");
  }, [phrase]);

  const canDelete = typedPhrase === phrase && !pending;

  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-slate-950/50 p-4"
      role="presentation"
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-documents-title"
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl"
      >
        <h2 id="delete-documents-title" className="text-lg font-semibold text-slate-950">
          Permanently delete {documentLabel(count)}?
        </h2>

        <p className="mt-2 text-sm leading-6 text-slate-600">
          This permanently deletes the selected documents and cannot be undone.
        </p>

        <label htmlFor="delete-confirmation" className="mt-5 block text-sm font-medium text-slate-800">
          Type <code className="rounded bg-slate-100 px-1 py-0.5 text-xs">{phrase}</code> to
          enable deletion.
        </label>
        <input
          id="delete-confirmation"
          autoFocus
          value={typedPhrase}
          disabled={pending}
          onChange={(event) => setTypedPhrase(event.currentTarget.value)}
          className="mt-2 w-full rounded-md border border-slate-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-red-500 focus:ring-2 focus:ring-red-200 disabled:bg-slate-100"
        />

        {error && (
          <p role="alert" className="mt-3 text-sm text-red-700">
            {error}
          </p>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            disabled={pending}
            onClick={onCancel}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!canDelete}
            onClick={onConfirm}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {pending ? "Deleting…" : `Delete ${documentLabel(count)}`}
          </button>
        </div>
      </section>
    </div>
  );
}

export function DocumentsTable({
  page,
  scope,
  onReload,
}: DocumentsTableProps) {
  const [selection, setSelection] = useState<Selection>(emptySelection);
  const [mutation, setMutation] = useState<MutationKind>("idle");
  const [error, setError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [undo, setUndo] = useState<{
    operationId: string;
    count: number;
  } | null>(null);

  // Selection cannot silently carry across a changed search/filter scope.
  useEffect(() => {
    setSelection(emptySelection());
    setDeleteOpen(false);
    setError(null);
  }, [scope.id]);

  const activeSelection =
    selection.kind === "allMatching" && selection.scopeId !== scope.id
      ? emptySelection()
      : selection;

  const selectedCount = selectionCount(activeSelection, scope);
  const busy = mutation !== "idle";
  const pageSelectedCount = page.items.filter((item) =>
    isSelected(activeSelection, item.id),
  ).length;
  const pageFullySelected =
    page.items.length > 0 && pageSelectedCount === page.items.length;

  function toggleRow(id: string, checked: boolean) {
    setSelection((current) => {
      if (current.kind === "ids") {
        const ids = new Set(current.ids);
        checked ? ids.add(id) : ids.delete(id);
        return { kind: "ids", ids };
      }

      const excludedIds = new Set(current.excludedIds);
      checked ? excludedIds.delete(id) : excludedIds.add(id);
      return { ...current, excludedIds };
    });
  }

  function togglePage(checked: boolean) {
    setSelection((current) => {
      if (current.kind === "ids") {
        const ids = new Set(current.ids);
        for (const item of page.items) {
          checked ? ids.add(item.id) : ids.delete(item.id);
        }
        return { kind: "ids", ids };
      }

      const excludedIds = new Set(current.excludedIds);
      for (const item of page.items) {
        checked ? excludedIds.delete(item.id) : excludedIds.add(item.id);
      }
      return { ...current, excludedIds };
    });
  }

  function selectAllMatching() {
    setSelection({
      kind: "allMatching",
      scopeId: scope.id,
      excludedIds: new Set(),
    });
  }

  async function archiveSelected() {
    const payload = selectionPayload(activeSelection, scope);
    if (!payload || busy) return;

    setError(null);
    setMutation("archiving");

    try {
      const result = await postJson<BulkMutationResult>(
        "/api/documents/bulk/archive",
        {
          selection: payload,
          // The server must store and replay this request idempotently.
          idempotencyKey: crypto.randomUUID(),
        },
      );

      setSelection(emptySelection());
      setUndo({ operationId: result.operationId, count: result.affectedCount });
      await onReload?.();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not archive documents.");
    } finally {
      setMutation("idle");
    }
  }

  async function deleteSelected() {
    const payload = selectionPayload(activeSelection, scope);
    if (!payload || busy) return;

    setError(null);
    setMutation("deleting");

    try {
      await postJson<BulkMutationResult>("/api/documents/bulk/delete", {
        selection: payload,
        idempotencyKey: crypto.randomUUID(),
      });

      setSelection(emptySelection());
      setDeleteOpen(false);
      await onReload?.();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete documents.");
    } finally {
      setMutation("idle");
    }
  }

  async function undoArchive() {
    if (!undo || busy) return;

    setError(null);
    setMutation("undoing");

    try {
      await postJson<BulkMutationResult>(
        `/api/document-bulk-operations/${encodeURIComponent(undo.operationId)}/undo`,
        { idempotencyKey: crypto.randomUUID() },
      );

      setUndo(null);
      await onReload?.();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not undo the archive.");
    } finally {
      setMutation("idle");
    }
  }

  return (
    <div className="space-y-3">
      {selectedCount > 0 && (
        <div
          className="sticky top-3 z-20 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 shadow-sm"
          aria-live="polite"
        >
          <div className="text-sm font-medium text-indigo-950">
            {activeSelection.kind === "allMatching"
              ? `${documentLabel(selectedCount)} matching the current filters selected`
              : `${documentLabel(selectedCount)} selected`}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={archiveSelected}
              className="rounded-md bg-white px-3 py-2 text-sm font-semibold text-slate-800 shadow-sm ring-1 ring-inset ring-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {mutation === "archiving" ? "Archiving…" : "Archive"}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setError(null);
                setDeleteOpen(true);
              }}
              className="rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Delete
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => setSelection(emptySelection())}
              className="px-2 py-2 text-sm font-medium text-indigo-800 hover:text-indigo-950 disabled:opacity-60"
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {activeSelection.kind === "ids" &&
        pageFullySelected &&
        scope.total > page.items.length && (
          <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-950">
            All {page.items.length} documents on this page are selected.{" "}
            <button
              type="button"
              disabled={busy}
              onClick={selectAllMatching}
              className="font-semibold underline underline-offset-2 hover:text-indigo-700 disabled:opacity-60"
            >
              Select all {scope.total.toLocaleString()} matching documents
            </button>
          </div>
        )}

      {error && !deleteOpen && (
        <p role="alert" className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-800">
          {error}
        </p>
      )}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              <th className="w-12 px-4 py-3 text-left">
                <PageSelectionCheckbox
                  checked={pageFullySelected}
                  indeterminate={pageSelectedCount > 0 && !pageFullySelected}
                  disabled={busy || page.items.length === 0}
                  onChange={togglePage}
                />
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                Title
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                Owner
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                Updated
              </th>
            </tr>
          </thead>

          <tbody className="divide-y divide-slate-100">
            {page.items.map((document) => (
              <tr key={document.id} className="hover:bg-slate-50">
                <td className="px-4 py-3">
                  <input
                    type="checkbox"
                    checked={isSelected(activeSelection, document.id)}
                    disabled={busy}
                    aria-label={`Select ${document.title}`}
                    onChange={(event) =>
                      toggleRow(document.id, event.currentTarget.checked)
                    }
                    className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 disabled:cursor-not-allowed"
                  />
                </td>
                <td className="px-4 py-3 text-sm font-medium text-slate-900">
                  {document.title}
                </td>
                <td className="px-4 py-3 text-sm text-slate-600">
                  {document.ownerName}
                </td>
                <td className="px-4 py-3 text-sm text-slate-600">
                  {new Date(document.updatedAt).toLocaleDateString()}
                </td>
              </tr>
            ))}

            {page.items.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-sm text-slate-500">
                  No documents match the current filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {undo && (
        <div
          role="status"
          className="fixed bottom-4 left-1/2 z-50 flex w-[min(32rem,calc(100%-2rem))] -translate-x-1/2 items-center justify-between gap-4 rounded-xl bg-slate-950 px-4 py-3 text-sm text-white shadow-xl"
        >
          <span>Archived {documentLabel(undo.count)}.</span>
          <button
            type="button"
            disabled={busy}
            onClick={undoArchive}
            className="font-semibold text-indigo-300 hover:text-indigo-200 disabled:opacity-60"
          >
            {mutation === "undoing" ? "Undoing…" : "Undo"}
          </button>
        </div>
      )}

      {deleteOpen && (
        <DeleteDialog
          count={selectedCount}
          pending={mutation === "deleting"}
          error={error}
          onCancel={() => {
            if (!busy) {
              setDeleteOpen(false);
              setError(null);
            }
          }}
          onConfirm={deleteSelected}
        />
      )}
    </div>
  );
}
```

The page checkbox can only select the visible 50 rows; selecting every matching document requires an explicit second action tied to an immutable server scope. Archive is recoverable through Undo, while Delete requires typing the exact affected count. Buttons and checkboxes lock during requests, and every mutation includes an idempotency key—backed by server-side idempotency storage—to prevent duplicate bulk operations.