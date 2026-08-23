```tsx
import { useEffect, useMemo, useRef, useState } from "react";

export type Document = {
  id: string;
  title: string;
  updatedAt: string;
  ownerName: string;
};

export type DocumentQuery = {
  search?: string;
  ownerId?: string;
};

type DocumentPage = {
  items: Document[];
  total: number;
  page: number;
  pageSize: number;
};

type BulkAction = "archive" | "delete";

type BulkSelection =
  | { mode: "ids"; ids: string[] }
  | {
      mode: "allMatching";
      query: DocumentQuery;
      excludedIds: string[];
      expectedTotal: number;
    };

type SelectionState =
  | { mode: "ids"; ids: ReadonlySet<string> }
  | {
      mode: "allMatching";
      query: DocumentQuery;
      excludedIds: ReadonlySet<string>;
      expectedTotal: number;
    };

type BulkActionResult = {
  operationId: string;
  affectedCount: number;
  // Required for archive so the UI can offer a real undo window.
  undoExpiresAt?: string;
};

const PAGE_SIZE = 50;

async function fetchDocuments(
  query: DocumentQuery,
  page: number,
  signal: AbortSignal,
): Promise<DocumentPage> {
  const params = new URLSearchParams({
    page: String(page),
    pageSize: String(PAGE_SIZE),
  });

  if (query.search) params.set("search", query.search);
  if (query.ownerId) params.set("ownerId", query.ownerId);

  const response = await fetch(`/api/documents?${params}`, { signal });

  if (!response.ok) {
    throw new Error("Could not load documents.");
  }

  return response.json();
}

async function mutateDocuments(
  action: BulkAction,
  selection: BulkSelection,
): Promise<BulkActionResult> {
  const response = await fetch("/api/documents/bulk", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      // The server must persist and replay a result for this key.
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({ action, selection }),
  });

  const body = await response.json().catch(() => ({}));

  if (!response.ok) {
    // A 409 should be returned if expectedTotal no longer matches the query.
    throw new Error(body.error ?? "The bulk action could not be completed.");
  }

  return body as BulkActionResult;
}

async function undoBulkArchive(operationId: string): Promise<void> {
  const response = await fetch(`/api/documents/bulk/${operationId}/undo`, {
    method: "POST",
    headers: {
      "Idempotency-Key": crypto.randomUUID(),
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error ?? "Could not undo the archive.");
  }
}

function selectionPayload(selection: SelectionState): BulkSelection {
  if (selection.mode === "ids") {
    return { mode: "ids", ids: [...selection.ids] };
  }

  return {
    mode: "allMatching",
    query: selection.query,
    excludedIds: [...selection.excludedIds],
    expectedTotal: selection.expectedTotal,
  };
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
  const [confirmation, setConfirmation] = useState("");
  const requiredText = `DELETE ${count}`;
  const canDelete = confirmation === requiredText && !pending;

  return (
    <div
      aria-labelledby="delete-title"
      aria-modal="true"
      className="fixed inset-0 z-50 grid place-items-center bg-slate-950/50 p-4"
      role="dialog"
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl">
        <h2 id="delete-title" className="text-lg font-semibold text-slate-900">
          Delete {count.toLocaleString()} document{count === 1 ? "" : "s"}?
        </h2>

        <p className="mt-2 text-sm text-slate-600">
          This permanently deletes the selected documents. Type{" "}
          <code className="rounded bg-slate-100 px-1 py-0.5 font-medium text-slate-900">
            {requiredText}
          </code>{" "}
          to continue.
        </p>

        <label className="mt-5 block text-sm font-medium text-slate-700">
          Confirmation
          <input
            autoComplete="off"
            className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 shadow-sm outline-none focus:border-red-500 focus:ring-2 focus:ring-red-200"
            disabled={pending}
            onChange={(event) => setConfirmation(event.target.value)}
            value={confirmation}
          />
        </label>

        {error && (
          <p className="mt-3 text-sm text-red-700" role="alert">
            {error}
          </p>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <button
            autoFocus
            className="rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
            disabled={pending}
            onClick={onCancel}
            type="button"
          >
            Cancel
          </button>
          <button
            className="rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
            disabled={!canDelete}
            onClick={onConfirm}
            type="button"
          >
            {pending ? "Deleting…" : "Delete permanently"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function DocumentsTable({ query = {} }: { query?: DocumentQuery }) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState<DocumentPage | null>(null);
  const [selection, setSelection] = useState<SelectionState>({
    mode: "ids",
    ids: new Set(),
  });
  const [loading, setLoading] = useState(true);
  const [mutating, setMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [undo, setUndo] = useState<{
    operationId: string;
    expiresAt: string;
    count: number;
  } | null>(null);

  const headerCheckbox = useRef<HTMLInputElement>(null);
  const queryKey = JSON.stringify(query);

  useEffect(() => {
    // A selection never silently carries into a different matching query.
    setPage(1);
    setSelection({ mode: "ids", ids: new Set() });
  }, [queryKey]);

  useEffect(() => {
    const controller = new AbortController();

    setLoading(true);
    setError(null);

    fetchDocuments(query, page, controller.signal)
      .then(setData)
      .catch((cause: unknown) => {
        if ((cause as Error).name !== "AbortError") {
          setError(cause instanceof Error ? cause.message : "Could not load documents.");
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [page, queryKey, reloadToken]);

  useEffect(() => {
    if (!undo) return;

    const timeout = window.setTimeout(
      () => setUndo(null),
      Math.max(0, new Date(undo.expiresAt).getTime() - Date.now()),
    );

    return () => window.clearTimeout(timeout);
  }, [undo]);

  const documents = data?.items ?? [];
  const total = data?.total ?? 0;

  const isSelected = (id: string) =>
    selection.mode === "ids"
      ? selection.ids.has(id)
      : !selection.excludedIds.has(id);

  const selectedCount = useMemo(() => {
    return selection.mode === "ids"
      ? selection.ids.size
      : Math.max(0, selection.expectedTotal - selection.excludedIds.size);
  }, [selection]);

  const pageFullySelected =
    documents.length > 0 && documents.every((document) => isSelected(document.id));

  const pagePartiallySelected =
    documents.some((document) => isSelected(document.id)) && !pageFullySelected;

  useEffect(() => {
    if (headerCheckbox.current) {
      headerCheckbox.current.indeterminate = pagePartiallySelected;
    }
  }, [pagePartiallySelected]);

  function toggleDocument(id: string) {
    setSelection((current) => {
      if (current.mode === "ids") {
        const ids = new Set(current.ids);
        ids.has(id) ? ids.delete(id) : ids.add(id);
        return { mode: "ids", ids };
      }

      const excludedIds = new Set(current.excludedIds);
      excludedIds.has(id) ? excludedIds.delete(id) : excludedIds.add(id);
      return { ...current, excludedIds };
    });
  }

  function togglePage() {
    const shouldSelect = !pageFullySelected;

    setSelection((current) => {
      if (current.mode === "ids") {
        const ids = new Set(current.ids);
        for (const document of documents) {
          shouldSelect ? ids.add(document.id) : ids.delete(document.id);
        }
        return { mode: "ids", ids };
      }

      const excludedIds = new Set(current.excludedIds);
      for (const document of documents) {
        shouldSelect ? excludedIds.delete(document.id) : excludedIds.add(document.id);
      }
      return { ...current, excludedIds };
    });
  }

  function selectAllMatching() {
    setSelection({
      mode: "allMatching",
      query,
      excludedIds: new Set(),
      expectedTotal: total,
    });
  }

  function clearSelection() {
    setSelection({ mode: "ids", ids: new Set() });
  }

  async function runBulkAction(action: BulkAction) {
    const snapshot = selectionPayload(selection);

    setMutating(true);
    setError(null);

    try {
      const result = await mutateDocuments(action, snapshot);

      clearSelection();
      setDeleteOpen(false);
      setReloadToken((token) => token + 1);

      if (action === "archive" && result.undoExpiresAt) {
        setUndo({
          operationId: result.operationId,
          expiresAt: result.undoExpiresAt,
          count: result.affectedCount,
        });
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Bulk action failed.");
    } finally {
      setMutating(false);
    }
  }

  async function handleUndo() {
    if (!undo) return;

    setMutating(true);
    setError(null);

    try {
      await undoBulkArchive(undo.operationId);
      setUndo(null);
      setReloadToken((token) => token + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Undo failed.");
    } finally {
      setMutating(false);
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const showSelectAllMatching =
    selection.mode === "ids" &&
    pageFullySelected &&
    total > documents.length;

  return (
    <section className="relative">
      {selectedCount > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm">
          <span className="text-sm font-semibold text-slate-900">
            {selectedCount.toLocaleString()} selected
          </span>

          <button
            className="rounded-md bg-slate-900 px-3 py-2 text-sm font-semibold text-white hover:bg-slate-700 disabled:opacity-50"
            disabled={mutating}
            onClick={() => runBulkAction("archive")}
            type="button"
          >
            {mutating ? "Working…" : "Archive"}
          </button>

          <button
            className="rounded-md px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
            disabled={mutating}
            onClick={() => setDeleteOpen(true)}
            type="button"
          >
            Delete
          </button>

          <button
            className="ml-auto text-sm font-medium text-slate-600 hover:text-slate-900"
            disabled={mutating}
            onClick={clearSelection}
            type="button"
          >
            Clear selection
          </button>
        </div>
      )}

      {showSelectAllMatching && (
        <div className="mb-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
          All {documents.length} documents on this page are selected.{" "}
          <button
            className="font-semibold underline underline-offset-2"
            disabled={mutating}
            onClick={selectAllMatching}
            type="button"
          >
            Select all {total.toLocaleString()} matching documents
          </button>
          .
        </div>
      )}

      {selection.mode === "allMatching" && (
        <div className="mb-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900">
          All {selectedCount.toLocaleString()} matching documents are selected.
        </div>
      )}

      {error && (
        <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">
          {error}
        </p>
      )}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              <th className="w-12 px-4 py-3">
                <input
                  ref={headerCheckbox}
                  aria-label="Select documents on this page"
                  checked={pageFullySelected}
                  className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-500"
                  disabled={loading || mutating || documents.length === 0}
                  onChange={togglePage}
                  type="checkbox"
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
            {loading &&
              Array.from({ length: 6 }).map((_, index) => (
                <tr key={index} className="animate-pulse">
                  <td className="px-4 py-4"><div className="h-4 w-4 rounded bg-slate-200" /></td>
                  <td className="px-4 py-4"><div className="h-4 w-64 rounded bg-slate-200" /></td>
                  <td className="px-4 py-4"><div className="h-4 w-28 rounded bg-slate-200" /></td>
                  <td className="px-4 py-4"><div className="h-4 w-24 rounded bg-slate-200" /></td>
                </tr>
              ))}

            {!loading &&
              documents.map((document) => (
                <tr key={document.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <input
                      aria-label={`Select ${document.title}`}
                      checked={isSelected(document.id)}
                      className="h-4 w-4 rounded border-slate-300 text-slate-900 focus:ring-slate-500"
                      disabled={mutating}
                      onChange={() => toggleDocument(document.id)}
                      type="checkbox"
                    />
                  </td>
                  <td className="px-4 py-3 text-sm font-medium text-slate-900">
                    {document.title}
                  </td>
                  <td className="px-4 py-3 text-sm text-slate-600">{document.ownerName}</td>
                  <td className="px-4 py-3 text-sm text-slate-600">
                    {new Intl.DateTimeFormat(undefined, {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(document.updatedAt))}
                  </td>
                </tr>
              ))}

            {!loading && documents.length === 0 && (
              <tr>
                <td className="px-4 py-10 text-center text-sm text-slate-500" colSpan={4}>
                  No documents match this view.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        <footer className="flex items-center justify-between border-t border-slate-200 px-4 py-3">
          <p className="text-sm text-slate-600">
            {total.toLocaleString()} matching documents
          </p>

          <div className="flex items-center gap-3">
            <button
              className="rounded px-2 py-1 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40"
              disabled={page === 1 || loading || mutating}
              onClick={() => setPage((current) => current - 1)}
              type="button"
            >
              Previous
            </button>
            <span className="text-sm text-slate-600">
              Page {page} of {totalPages}
            </span>
            <button
              className="rounded px-2 py-1 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-40"
              disabled={page >= totalPages || loading || mutating}
              onClick={() => setPage((current) => current + 1)}
              type="button"
            >
              Next
            </button>
          </div>
        </footer>
      </div>

      {deleteOpen && (
        <DeleteDialog
          count={selectedCount}
          error={error}
          pending={mutating}
          onCancel={() => !mutating && setDeleteOpen(false)}
          onConfirm={() => runBulkAction("delete")}
        />
      )}

      {undo && (
        <div
          className="fixed bottom-5 left-1/2 z-40 flex -translate-x-1/2 items-center gap-4 rounded-lg bg-slate-900 px-4 py-3 text-sm text-white shadow-xl"
          role="status"
        >
          <span>
            Archived {undo.count.toLocaleString()} document{undo.count === 1 ? "" : "s"}.
          </span>
          <button
            className="font-semibold underline underline-offset-2 disabled:opacity-50"
            disabled={mutating}
            onClick={handleUndo}
            type="button"
          >
            Undo
          </button>
        </div>
      )}
    </section>
  );
}
```

The selection model distinguishes the visible 50 rows from all matching rows, so “select all” never silently targets thousands. Archive is reversible through a server-backed undo window; permanent deletion requires the exact affected count to be typed. Both mutation paths carry required idempotency keys; the API should enforce authorization, query scoping, and `expectedTotal` atomically.