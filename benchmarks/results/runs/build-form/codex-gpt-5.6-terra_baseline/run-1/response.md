```tsx
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
} from "react";

export type Document = {
  id: string;
  title: string;
  updatedAt: string;
  ownerName: string;
};

export type DocumentPage = {
  documents: Document[];
  totalMatching: number;
};

export type DocumentQuery = Record<string, unknown>;

type ExplicitSelection = {
  kind: "ids";
  ids: Set<string>;
};

type AllMatchingSelection = {
  kind: "all-matching";
  excludedIds: Set<string>;
};

type Selection = ExplicitSelection | AllMatchingSelection;

type BulkAction = "archive" | "delete";

type BulkSelectionPayload =
  | { kind: "ids"; ids: string[] }
  | { kind: "all-matching"; query: DocumentQuery; excludedIds: string[] };

type BulkMutationResult = {
  affectedCount?: number;
  jobId?: string;
};

type DocumentsTableProps = {
  /**
   * Must contain every filter/sort constraint that defines "matching documents".
   * The server must apply authorization and this query again for bulk operations.
   */
  matchingQuery: DocumentQuery;

  /**
   * Change this whenever matchingQuery changes. For example:
   * JSON.stringify({ search, ownerId, sort })
   */
  selectionKey: string;

  /**
   * Fetches exactly one page. Memoize this function in the parent with useCallback.
   */
  loadPage: (input: {
    page: number;
    pageSize: number;
    query: DocumentQuery;
    signal: AbortSignal;
  }) => Promise<DocumentPage>;

  /**
   * Called after a successful archive/delete mutation.
   */
  onBulkComplete?: (result: BulkMutationResult) => void;
};

const PAGE_SIZE = 50;

function emptySelection(): ExplicitSelection {
  return { kind: "ids", ids: new Set() };
}

function isSelected(selection: Selection, id: string) {
  return selection.kind === "ids"
    ? selection.ids.has(id)
    : !selection.excludedIds.has(id);
}

function selectedCount(selection: Selection, totalMatching: number) {
  return selection.kind === "ids"
    ? selection.ids.size
    : Math.max(0, totalMatching - selection.excludedIds.size);
}

function toBulkSelectionPayload(
  selection: Selection,
  matchingQuery: DocumentQuery,
): BulkSelectionPayload {
  if (selection.kind === "ids") {
    return { kind: "ids", ids: [...selection.ids] };
  }

  return {
    kind: "all-matching",
    query: matchingQuery,
    excludedIds: [...selection.excludedIds],
  };
}

/**
 * Server contract:
 *
 * POST /api/documents/bulk
 * {
 *   action: "archive" | "delete",
 *   selection:
 *     | { kind: "ids", ids: string[] }
 *     | { kind: "all-matching", query: {...}, excludedIds: string[] }
 * }
 *
 * For all-matching selections, the server should resolve the query within the
 * current user's authorized tenant and ideally queue a background job.
 */
async function runBulkMutation(
  action: BulkAction,
  selection: BulkSelectionPayload,
): Promise<BulkMutationResult> {
  const response = await fetch("/api/documents/bulk", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, selection }),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.message ?? "The bulk action could not be completed.");
  }

  return response.json().catch(() => ({}));
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
  onChange: (event: ChangeEvent<HTMLInputElement>) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (inputRef.current) inputRef.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <input
      ref={inputRef}
      type="checkbox"
      aria-label="Select all documents on this page"
      checked={checked}
      disabled={disabled}
      onChange={onChange}
      className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 disabled:cursor-not-allowed"
    />
  );
}

export function DocumentsTable({
  matchingQuery,
  selectionKey,
  loadPage,
  onBulkComplete,
}: DocumentsTableProps) {
  const [page, setPage] = useState(1);
  const [pageData, setPageData] = useState<DocumentPage>({
    documents: [],
    totalMatching: 0,
  });
  const [selection, setSelection] = useState<Selection>(emptySelection);
  const [isLoading, setIsLoading] = useState(true);
  const [isMutating, setIsMutating] = useState(false);
  const [reloadVersion, setReloadVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // A changed filter/sort represents a different result set.
  useEffect(() => {
    setPage(1);
    setSelection(emptySelection());
    setConfirmDelete(false);
  }, [selectionKey]);

  useEffect(() => {
    const controller = new AbortController();

    setIsLoading(true);
    setError(null);

    loadPage({
      page,
      pageSize: PAGE_SIZE,
      query: matchingQuery,
      signal: controller.signal,
    })
      .then((result) => {
        if (!controller.signal.aborted) setPageData(result);
      })
      .catch((cause: unknown) => {
        if (!controller.signal.aborted) {
          setError(
            cause instanceof Error
              ? cause.message
              : "Documents could not be loaded.",
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });

    return () => controller.abort();
  }, [page, matchingQuery, loadPage, reloadVersion]);

  const { documents, totalMatching } = pageData;
  const pageIds = useMemo(() => documents.map((document) => document.id), [documents]);

  const count = selectedCount(selection, totalMatching);
  const allOnPageSelected =
    pageIds.length > 0 && pageIds.every((id) => isSelected(selection, id));
  const someOnPageSelected =
    !allOnPageSelected && pageIds.some((id) => isSelected(selection, id));
  const totalPages = Math.max(1, Math.ceil(totalMatching / PAGE_SIZE));

  function toggleDocument(id: string, checked: boolean) {
    setSelection((current) => {
      if (current.kind === "ids") {
        const ids = new Set(current.ids);
        checked ? ids.add(id) : ids.delete(id);
        return { kind: "ids", ids };
      }

      const excludedIds = new Set(current.excludedIds);
      checked ? excludedIds.delete(id) : excludedIds.add(id);
      return { kind: "all-matching", excludedIds };
    });
  }

  function toggleCurrentPage(checked: boolean) {
    setSelection((current) => {
      if (current.kind === "ids") {
        const ids = new Set(current.ids);
        for (const id of pageIds) checked ? ids.add(id) : ids.delete(id);
        return { kind: "ids", ids };
      }

      const excludedIds = new Set(current.excludedIds);
      for (const id of pageIds) checked ? excludedIds.delete(id) : excludedIds.add(id);
      return { kind: "all-matching", excludedIds };
    });
  }

  function selectAllMatching() {
    setSelection({ kind: "all-matching", excludedIds: new Set() });
  }

  async function executeBulkAction(action: BulkAction) {
    if (count === 0 || isMutating) return;

    setIsMutating(true);
    setError(null);

    try {
      const result = await runBulkMutation(
        action,
        toBulkSelectionPayload(selection, matchingQuery),
      );

      setSelection(emptySelection());
      setConfirmDelete(false);
      setReloadVersion((value) => value + 1);
      onBulkComplete?.(result);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "The bulk action could not be completed.",
      );
    } finally {
      setIsMutating(false);
    }
  }

  return (
    <section className="space-y-4">
      {count > 0 ? (
        <div
          className="sticky top-3 z-10 flex flex-wrap items-center gap-3 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3 shadow-sm"
          role="status"
        >
          <span className="text-sm font-medium text-indigo-950">
            {count.toLocaleString()} document{count === 1 ? "" : "s"} selected
          </span>

          <button
            type="button"
            disabled={isMutating}
            onClick={() => void executeBulkAction("archive")}
            className="rounded-md bg-white px-3 py-1.5 text-sm font-medium text-slate-800 shadow-sm ring-1 ring-inset ring-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isMutating ? "Working…" : "Archive"}
          </button>

          {confirmDelete ? (
            <>
              <span className="text-sm text-slate-700">Delete permanently?</span>
              <button
                type="button"
                disabled={isMutating}
                onClick={() => void executeBulkAction("delete")}
                className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Confirm delete
              </button>
              <button
                type="button"
                disabled={isMutating}
                onClick={() => setConfirmDelete(false)}
                className="text-sm font-medium text-slate-700 hover:text-slate-950"
              >
                Cancel
              </button>
            </>
          ) : (
            <button
              type="button"
              disabled={isMutating}
              onClick={() => setConfirmDelete(true)}
              className="rounded-md px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Delete
            </button>
          )}

          <button
            type="button"
            disabled={isMutating}
            onClick={() => setSelection(emptySelection())}
            className="ml-auto text-sm font-medium text-slate-700 hover:text-slate-950 disabled:opacity-50"
          >
            Clear selection
          </button>
        </div>
      ) : null}

      {selection.kind === "ids" &&
      allOnPageSelected &&
      totalMatching > documents.length ? (
        <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-950">
          All {documents.length} documents on this page are selected.{" "}
          <button
            type="button"
            onClick={selectAllMatching}
            className="font-semibold underline underline-offset-2"
          >
            Select all {totalMatching.toLocaleString()} matching documents
          </button>
          .
        </div>
      ) : null}

      {error ? (
        <div
          className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="w-12 px-4 py-3">
                <PageSelectionCheckbox
                  checked={allOnPageSelected}
                  indeterminate={someOnPageSelected}
                  disabled={isLoading || isMutating || documents.length === 0}
                  onChange={(event) => toggleCurrentPage(event.target.checked)}
                />
              </th>
              <th className="px-4 py-3 font-medium">Title</th>
              <th className="px-4 py-3 font-medium">Owner</th>
              <th className="px-4 py-3 font-medium">Updated</th>
            </tr>
          </thead>

          <tbody className="divide-y divide-slate-200">
            {isLoading ? (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-slate-500">
                  Loading documents…
                </td>
              </tr>
            ) : documents.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-slate-500">
                  No matching documents.
                </td>
              </tr>
            ) : (
              documents.map((document) => {
                const checked = isSelected(selection, document.id);

                return (
                  <tr
                    key={document.id}
                    className={checked ? "bg-indigo-50/60" : "hover:bg-slate-50"}
                  >
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        aria-label={`Select ${document.title}`}
                        checked={checked}
                        disabled={isMutating}
                        onChange={(event) =>
                          toggleDocument(document.id, event.target.checked)
                        }
                        className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 disabled:cursor-not-allowed"
                      />
                    </td>
                    <td className="px-4 py-3 font-medium text-slate-900">
                      {document.title}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {document.ownerName}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {new Date(document.updatedAt).toLocaleDateString()}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        <footer className="flex items-center justify-between border-t border-slate-200 px-4 py-3">
          <p className="text-sm text-slate-600">
            {totalMatching.toLocaleString()} matching document
            {totalMatching === 1 ? "" : "s"}
          </p>

          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={page === 1 || isLoading}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-sm text-slate-600">
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              disabled={page === totalPages || isLoading}
              onClick={() =>
                setPage((current) => Math.min(totalPages, current + 1))
              }
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </footer>
      </div>
    </section>
  );
}
```

This keeps normal selections in a `Set` and uses an “all matching except these IDs” representation when selecting thousands of results, so the browser never has to download or retain every matching document ID.