Assumptions: the API supports server-side bulk mutations against a stable `selectionToken`, and “Delete” is a soft delete (restorable for 30 days). This avoids sending thousands of IDs to the browser and keeps a bulk action’s target set stable.

```tsx
import React, { useEffect, useMemo, useRef, useState } from "react";

export type Document = {
  id: string;
  title: string;
  updatedAt: string;
  ownerName: string;
};

type DocumentsPage = {
  items: Document[];
  totalMatching: number;
  /**
   * Opaque server-issued snapshot for the current filters/sort/search.
   * The server uses it to apply bulk actions to the same matching set
   * the user selected, even if records change after the page loaded.
   */
  selectionToken: string;
};

type Filters = {
  search: string;
  ownerId?: string;
  sort?: "updatedAt-desc" | "updatedAt-asc";
};

type ExplicitSelection = {
  kind: "explicit";
  ids: Set<string>;
};

type AllMatchingSelection = {
  kind: "allMatching";
  selectionToken: string;
  totalMatching: number;
  excludedIds: Set<string>;
};

type Selection = ExplicitSelection | AllMatchingSelection;

type BulkTarget =
  | { kind: "ids"; ids: string[] }
  | {
      kind: "matching";
      selectionToken: string;
      excludedIds: string[];
    };

type BulkAction = "archive" | "delete";

type BulkMutationResponse = {
  affectedCount: number;
  undoToken?: string;
};

async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.message ?? "Request failed.");
  }

  return response.json() as Promise<T>;
}

async function fetchDocuments(
  filters: Filters,
  page: number,
): Promise<DocumentsPage> {
  const params = new URLSearchParams({
    page: String(page),
    pageSize: "50",
    search: filters.search,
    ...(filters.ownerId ? { ownerId: filters.ownerId } : {}),
    ...(filters.sort ? { sort: filters.sort } : {}),
  });

  return apiFetch<DocumentsPage>(`/api/documents?${params}`);
}

async function bulkMutateDocuments(
  action: BulkAction,
  target: BulkTarget,
  idempotencyKey: string,
): Promise<BulkMutationResponse> {
  return apiFetch<BulkMutationResponse>(`/api/documents/bulk/${action}`, {
    method: "POST",
    headers: {
      "Idempotency-Key": idempotencyKey,
    },
    body: JSON.stringify(target),
  });
}

async function undoBulkDelete(undoToken: string): Promise<void> {
  await apiFetch("/api/documents/bulk/undo-delete", {
    method: "POST",
    body: JSON.stringify({ undoToken }),
  });
}

function selectionCount(selection: Selection): number {
  return selection.kind === "explicit"
    ? selection.ids.size
    : selection.totalMatching - selection.excludedIds.size;
}

function isSelected(selection: Selection, document: Document): boolean {
  return selection.kind === "explicit"
    ? selection.ids.has(document.id)
    : !selection.excludedIds.has(document.id);
}

function toBulkTarget(selection: Selection): BulkTarget {
  if (selection.kind === "explicit") {
    return { kind: "ids", ids: [...selection.ids] };
  }

  return {
    kind: "matching",
    selectionToken: selection.selectionToken,
    excludedIds: [...selection.excludedIds],
  };
}

function formatCount(count: number): string {
  return new Intl.NumberFormat().format(count);
}

function ConfirmationDialog({
  action,
  count,
  onCancel,
  onConfirm,
  busy,
}: {
  action: BulkAction;
  count: number;
  onCancel(): void;
  onConfirm(): void;
  busy: boolean;
}) {
  const isDelete = action === "delete";

  return (
    <div
      aria-labelledby="bulk-confirmation-title"
      aria-modal="true"
      className="fixed inset-0 z-50 grid place-items-center bg-slate-950/50 p-4"
      role="dialog"
    >
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl">
        <h2
          className="text-lg font-semibold text-slate-950"
          id="bulk-confirmation-title"
        >
          {isDelete ? "Delete selected documents?" : "Archive selected documents?"}
        </h2>

        <p className="mt-2 text-sm leading-6 text-slate-600">
          {isDelete ? (
            <>
              <strong>{formatCount(count)} documents</strong> will move to Trash
              and can be restored for 30 days.
            </>
          ) : (
            <>
              <strong>{formatCount(count)} documents</strong> will be archived.
              They will remain available in the archive.
            </>
          )}
        </p>

        <div className="mt-6 flex justify-end gap-3">
          <button
            className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            disabled={busy}
            onClick={onCancel}
            type="button"
          >
            Cancel
          </button>

          <button
            className={
              isDelete
                ? "rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
                : "rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
            }
            disabled={busy}
            onClick={onConfirm}
            type="button"
          >
            {busy
              ? "Working…"
              : isDelete
                ? `Move ${formatCount(count)} to Trash`
                : `Archive ${formatCount(count)}`}
          </button>
        </div>
      </div>
    </div>
  );
}

function BulkActionsBar({
  selection,
  onClear,
  onArchive,
  onDelete,
  busy,
}: {
  selection: Selection;
  onClear(): void;
  onArchive(): void;
  onDelete(): void;
  busy: boolean;
}) {
  const count = selectionCount(selection);

  return (
    <div
      aria-live="polite"
      className="sticky bottom-4 z-20 mx-auto flex w-fit items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-lg"
    >
      <span className="text-sm font-medium text-slate-900">
        {formatCount(count)} selected
      </span>

      <button
        className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        disabled={busy}
        onClick={onClear}
        type="button"
      >
        Clear selection
      </button>

      <button
        className="rounded-md bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
        disabled={busy}
        onClick={onArchive}
        type="button"
      >
        Archive
      </button>

      <button
        className="rounded-md bg-red-600 px-3 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
        disabled={busy}
        onClick={onDelete}
        type="button"
      >
        Delete
      </button>
    </div>
  );
}

export function DocumentsTable() {
  const [filters] = useState<Filters>({
    search: "",
    sort: "updatedAt-desc",
  });
  const [page, setPage] = useState(1);
  const [data, setData] = useState<DocumentsPage | null>(null);
  const [selection, setSelection] = useState<Selection>({
    kind: "explicit",
    ids: new Set(),
  });
  const [pendingAction, setPendingAction] = useState<BulkAction | null>(null);
  const [isMutating, setIsMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [undo, setUndo] = useState<{ token: string; count: number } | null>(null);

  const headerCheckboxRef = useRef<HTMLInputElement>(null);

  async function refresh() {
    setError(null);

    try {
      const nextData = await fetchDocuments(filters, page);
      setData(nextData);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not load documents.",
      );
    }
  }

  useEffect(() => {
    void refresh();
  }, [page, filters.search, filters.ownerId, filters.sort]);

  const pageSelectionCount = useMemo(() => {
    if (!data) return 0;
    return data.items.filter((document) => isSelected(selection, document)).length;
  }, [data, selection]);

  const allPageRowsSelected = Boolean(
    data?.items.length && pageSelectionCount === data.items.length,
  );

  useEffect(() => {
    if (headerCheckboxRef.current) {
      headerCheckboxRef.current.indeterminate =
        pageSelectionCount > 0 && !allPageRowsSelected;
    }
  }, [pageSelectionCount, allPageRowsSelected]);

  function toggleRow(document: Document) {
    setSelection((current) => {
      if (current.kind === "explicit") {
        const ids = new Set(current.ids);
        ids.has(document.id) ? ids.delete(document.id) : ids.add(document.id);
        return { kind: "explicit", ids };
      }

      const excludedIds = new Set(current.excludedIds);
      excludedIds.has(document.id)
        ? excludedIds.delete(document.id)
        : excludedIds.add(document.id);

      return { ...current, excludedIds };
    });
  }

  function togglePage() {
    if (!data) return;

    setSelection((current) => {
      if (current.kind === "explicit") {
        const ids = new Set(current.ids);

        if (allPageRowsSelected) {
          data.items.forEach((document) => ids.delete(document.id));
        } else {
          data.items.forEach((document) => ids.add(document.id));
        }

        return { kind: "explicit", ids };
      }

      const excludedIds = new Set(current.excludedIds);

      if (allPageRowsSelected) {
        data.items.forEach((document) => excludedIds.add(document.id));
      } else {
        data.items.forEach((document) => excludedIds.delete(document.id));
      }

      return { ...current, excludedIds };
    });
  }

  function selectAllMatching() {
    if (!data) return;

    setSelection({
      kind: "allMatching",
      selectionToken: data.selectionToken,
      totalMatching: data.totalMatching,
      excludedIds: new Set(),
    });
  }

  async function runBulkAction() {
    if (!pendingAction || selectionCount(selection) === 0) return;

    setIsMutating(true);
    setError(null);

    try {
      const response = await bulkMutateDocuments(
        pendingAction,
        toBulkTarget(selection),
        crypto.randomUUID(),
      );

      const action = pendingAction;
      setPendingAction(null);
      setSelection({ kind: "explicit", ids: new Set() });

      if (action === "delete" && response.undoToken) {
        setUndo({ token: response.undoToken, count: response.affectedCount });
      }

      await refresh();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Bulk action could not be completed.",
      );
    } finally {
      setIsMutating(false);
    }
  }

  async function handleUndoDelete() {
    if (!undo) return;

    setIsMutating(true);
    setError(null);

    try {
      await undoBulkDelete(undo.token);
      setUndo(null);
      await refresh();
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Could not restore documents.",
      );
    } finally {
      setIsMutating(false);
    }
  }

  const selectedCount = selectionCount(selection);

  return (
    <section className="space-y-4">
      {error && (
        <div
          className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          role="alert"
        >
          {error}
        </div>
      )}

      {undo && (
        <div
          className="flex items-center justify-between gap-4 rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800"
          role="status"
        >
          <span>{formatCount(undo.count)} documents moved to Trash.</span>
          <button
            className="font-semibold text-slate-900 underline disabled:opacity-50"
            disabled={isMutating}
            onClick={() => void handleUndoDelete()}
            type="button"
          >
            Undo
          </button>
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="w-12 px-4 py-3">
                <input
                  aria-label="Select all documents on this page"
                  checked={allPageRowsSelected}
                  disabled={!data?.items.length || isMutating}
                  onChange={togglePage}
                  ref={headerCheckboxRef}
                  type="checkbox"
                />
              </th>
              <th className="px-4 py-3 font-medium">Title</th>
              <th className="px-4 py-3 font-medium">Owner</th>
              <th className="px-4 py-3 font-medium">Updated</th>
            </tr>
          </thead>

          <tbody>
            {data?.items.map((document) => (
              <tr
                className="border-t border-slate-100 hover:bg-slate-50"
                key={document.id}
              >
                <td className="px-4 py-3">
                  <input
                    aria-label={`Select ${document.title}`}
                    checked={isSelected(selection, document)}
                    disabled={isMutating}
                    onChange={() => toggleRow(document)}
                    type="checkbox"
                  />
                </td>
                <td className="px-4 py-3 font-medium text-slate-900">
                  {document.title}
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {document.ownerName}
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {new Intl.DateTimeFormat(undefined, {
                    dateStyle: "medium",
                    timeStyle: "short",
                  }).format(new Date(document.updatedAt))}
                </td>
              </tr>
            ))}

            {!data?.items.length && (
              <tr>
                <td className="px-4 py-10 text-center text-slate-500" colSpan={4}>
                  No documents found.
                </td>
              </tr>
            )}
          </tbody>
        </table>

        {data && selectedCount > 0 && selection.kind === "explicit" && (
          <div className="border-t border-slate-200 bg-blue-50 px-4 py-3 text-sm text-blue-950">
            All {formatCount(selectedCount)} documents on this page are selected.{" "}
            <button
              className="font-semibold underline disabled:opacity-50"
              disabled={isMutating}
              onClick={selectAllMatching}
              type="button"
            >
              Select all {formatCount(data.totalMatching)} matching documents
            </button>
          </div>
        )}

        {selection.kind === "allMatching" && (
          <div className="border-t border-slate-200 bg-blue-50 px-4 py-3 text-sm text-blue-950">
            All {formatCount(selectedCount)} matching documents are selected.
            {selection.excludedIds.size > 0 &&
              ` (${formatCount(selection.excludedIds.size)} excluded)`}
            <button
              className="ml-3 font-semibold underline disabled:opacity-50"
              disabled={isMutating}
              onClick={() =>
                setSelection({ kind: "explicit", ids: new Set() })
              }
              type="button"
            >
              Clear selection
            </button>
          </div>
        )}
      </div>

      <div className="flex justify-end gap-3">
        <button
          className="rounded-md border border-slate-300 px-3 py-2 text-sm disabled:opacity-50"
          disabled={page === 1 || isMutating}
          onClick={() => setPage((current) => current - 1)}
          type="button"
        >
          Previous
        </button>
        <button
          className="rounded-md border border-slate-300 px-3 py-2 text-sm disabled={isMutating}"
          disabled={isMutating}
          onClick={() => setPage((current) => current + 1)}
          type="button"
        >
          Next
        </button>
      </div>

      {selectedCount > 0 && (
        <BulkActionsBar
          busy={isMutating}
          onArchive={() => setPendingAction("archive")}
          onClear={() => setSelection({ kind: "explicit", ids: new Set() })}
          onDelete={() => setPendingAction("delete")}
          selection={selection}
        />
      )}

      {pendingAction && (
        <ConfirmationDialog
          action={pendingAction}
          busy={isMutating}
          count={selectedCount}
          onCancel={() => setPendingAction(null)}
          onConfirm={() => void runBulkAction()}
        />
      )}
    </section>
  );
}
```

The discriminated selection state prevents the dangerous ambiguity between “50 rows on this page” and “all matching documents.” Archive is recoverable; delete is explicitly scoped, count-confirmed, idempotent, disabled during submission, and paired with undo. The server must still authorize the bulk endpoint and bind the idempotency key to the mutation payload.