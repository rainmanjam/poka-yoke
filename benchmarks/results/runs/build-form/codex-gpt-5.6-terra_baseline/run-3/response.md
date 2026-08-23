```tsx
import React, { useEffect, useMemo, useRef, useState } from "react";

type Document = {
  id: string;
  title: string;
  updatedAt: string;
  ownerName: string;
};

type DocumentsResponse = {
  documents: Document[];
  total: number;
};

type BulkSelection =
  | { mode: "explicit"; ids: Set<string> }
  | { mode: "allMatching"; excludedIds: Set<string> };

type BulkAction = "archive" | "delete";

const PAGE_SIZE = 50;

async function getDocuments(
  page: number,
  filters: Record<string, string | number | boolean | undefined>,
  signal?: AbortSignal,
): Promise<DocumentsResponse> {
  const params = new URLSearchParams({
    page: String(page),
    pageSize: String(PAGE_SIZE),
  });

  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined) params.set(key, String(value));
  }

  const response = await fetch(`/api/documents?${params}`, { signal });

  if (!response.ok) {
    throw new Error("Could not load documents.");
  }

  return response.json();
}

/**
 * The API receives a compact selection description:
 * - explicit IDs for ordinary selection
 * - "allMatching" plus exclusions when selecting thousands of documents
 */
async function runBulkAction(
  action: BulkAction,
  selection: BulkSelection,
  filters: Record<string, string | number | boolean | undefined>,
): Promise<void> {
  const body =
    selection.mode === "explicit"
      ? {
          selection: {
            type: "ids",
            ids: [...selection.ids],
          },
        }
      : {
          selection: {
            type: "allMatching",
            filters,
            excludeIds: [...selection.excludedIds],
          },
        };

  const response = await fetch(`/api/documents/bulk/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Could not ${action} selected documents.`);
  }
}

function IndeterminateCheckbox(
  props: React.InputHTMLAttributes<HTMLInputElement> & {
    indeterminate?: boolean;
  },
) {
  const { indeterminate = false, ...inputProps } = props;
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <input
      ref={ref}
      type="checkbox"
      className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
      {...inputProps}
    />
  );
}

export function DocumentsTable({
  filters = {},
}: {
  /**
   * Pass the same filters used by the surrounding search UI.
   * They are sent to the server when "Select all matching" is used.
   */
  filters?: Record<string, string | number | boolean | undefined>;
}) {
  const [page, setPage] = useState(1);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [total, setTotal] = useState(0);
  const [selection, setSelection] = useState<BulkSelection>({
    mode: "explicit",
    ids: new Set(),
  });
  const [loading, setLoading] = useState(true);
  const [actionInFlight, setActionInFlight] = useState<BulkAction | null>(null);
  const [error, setError] = useState<string | null>(null);

  const filtersKey = JSON.stringify(filters);
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  useEffect(() => {
    setPage(1);
    setSelection({ mode: "explicit", ids: new Set() });
  }, [filtersKey]);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const result = await getDocuments(page, filters, controller.signal);
        setDocuments(result.documents);
        setTotal(result.total);

        // A deletion can leave the user on a now-empty final page.
        if (result.documents.length === 0 && page > 1) {
          setPage((current) => current - 1);
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          setError(err instanceof Error ? err.message : "Could not load documents.");
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }

    void load();
    return () => controller.abort();
  }, [page, filtersKey]);

  const selectedCount =
    selection.mode === "explicit"
      ? selection.ids.size
      : Math.max(0, total - selection.excludedIds.size);

  const selectedOnPage = useMemo(() => {
    if (selection.mode === "explicit") {
      return documents.filter((document) => selection.ids.has(document.id)).length;
    }

    return documents.filter(
      (document) => !selection.excludedIds.has(document.id),
    ).length;
  }, [documents, selection]);

  const pageIsFullySelected =
    documents.length > 0 && selectedOnPage === documents.length;

  const toggleDocument = (id: string, checked: boolean) => {
    setSelection((current) => {
      if (current.mode === "explicit") {
        const ids = new Set(current.ids);
        checked ? ids.add(id) : ids.delete(id);
        return { mode: "explicit", ids };
      }

      const excludedIds = new Set(current.excludedIds);
      checked ? excludedIds.delete(id) : excludedIds.add(id);
      return { mode: "allMatching", excludedIds };
    });
  };

  const togglePage = (checked: boolean) => {
    setSelection((current) => {
      if (current.mode === "explicit") {
        const ids = new Set(current.ids);

        for (const document of documents) {
          checked ? ids.add(document.id) : ids.delete(document.id);
        }

        return { mode: "explicit", ids };
      }

      const excludedIds = new Set(current.excludedIds);

      for (const document of documents) {
        checked
          ? excludedIds.delete(document.id)
          : excludedIds.add(document.id);
      }

      return { mode: "allMatching", excludedIds };
    });
  };

  const selectAllMatching = () => {
    setSelection({ mode: "allMatching", excludedIds: new Set() });
  };

  const clearSelection = () => {
    setSelection({ mode: "explicit", ids: new Set() });
  };

  const performBulkAction = async (action: BulkAction) => {
    if (selectedCount === 0) return;

    if (
      action === "delete" &&
      !window.confirm(
        `Permanently delete ${selectedCount.toLocaleString()} document${
          selectedCount === 1 ? "" : "s"
        }?`,
      )
    ) {
      return;
    }

    setActionInFlight(action);
    setError(null);

    try {
      await runBulkAction(action, selection, filters);
      clearSelection();

      // Reload this page to reflect the mutation.
      const result = await getDocuments(page, filters);
      setDocuments(result.documents);
      setTotal(result.total);

      if (result.documents.length === 0 && page > 1) {
        setPage((current) => current - 1);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not ${action} documents.`);
    } finally {
      setActionInFlight(null);
    }
  };

  return (
    <section className="mx-auto max-w-6xl p-6">
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        {selectedCount > 0 && (
          <div className="flex flex-col gap-3 border-b border-indigo-100 bg-indigo-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm font-medium text-indigo-950">
              {selectedCount.toLocaleString()} document
              {selectedCount === 1 ? "" : "s"} selected
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void performBulkAction("archive")}
                disabled={actionInFlight !== null}
                className="rounded-md bg-white px-3 py-2 text-sm font-semibold text-slate-800 shadow-sm ring-1 ring-inset ring-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {actionInFlight === "archive" ? "Archiving…" : "Archive"}
              </button>

              <button
                type="button"
                onClick={() => void performBulkAction("delete")}
                disabled={actionInFlight !== null}
                className="rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {actionInFlight === "delete" ? "Deleting…" : "Delete"}
              </button>

              <button
                type="button"
                onClick={clearSelection}
                disabled={actionInFlight !== null}
                className="px-2 py-2 text-sm font-medium text-slate-600 hover:text-slate-950 disabled:opacity-50"
              >
                Clear
              </button>
            </div>
          </div>
        )}

        {error && (
          <div role="alert" className="border-b border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th scope="col" className="w-12 px-4 py-3 text-left">
                  <IndeterminateCheckbox
                    aria-label="Select all documents on this page"
                    checked={pageIsFullySelected}
                    indeterminate={
                      selectedOnPage > 0 && selectedOnPage < documents.length
                    }
                    onChange={(event) => togglePage(event.target.checked)}
                    disabled={documents.length === 0 || actionInFlight !== null}
                  />
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Title
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Owner
                </th>
                <th scope="col" className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Updated
                </th>
              </tr>
            </thead>

            <tbody className="divide-y divide-slate-100 bg-white">
              {loading ? (
                <tr>
                  <td colSpan={4} className="px-4 py-12 text-center text-sm text-slate-500">
                    Loading documents…
                  </td>
                </tr>
              ) : documents.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-12 text-center text-sm text-slate-500">
                    No documents found.
                  </td>
                </tr>
              ) : (
                documents.map((document) => {
                  const checked =
                    selection.mode === "explicit"
                      ? selection.ids.has(document.id)
                      : !selection.excludedIds.has(document.id);

                  return (
                    <tr
                      key={document.id}
                      className={checked ? "bg-indigo-50/60" : "hover:bg-slate-50"}
                    >
                      <td className="px-4 py-4">
                        <IndeterminateCheckbox
                          aria-label={`Select ${document.title}`}
                          checked={checked}
                          onChange={(event) =>
                            toggleDocument(document.id, event.target.checked)
                          }
                          disabled={actionInFlight !== null}
                        />
                      </td>
                      <td className="px-4 py-4 text-sm font-medium text-slate-900">
                        {document.title}
                      </td>
                      <td className="px-4 py-4 text-sm text-slate-600">
                        {document.ownerName}
                      </td>
                      <td className="px-4 py-4 text-sm text-slate-600">
                        {new Intl.DateTimeFormat(undefined, {
                          dateStyle: "medium",
                        }).format(new Date(document.updatedAt))}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {selection.mode === "explicit" &&
          selectedCount > 0 &&
          selectedCount < total && (
            <div className="border-t border-indigo-100 bg-indigo-50 px-4 py-3 text-center text-sm text-indigo-950">
              All {selectedCount} documents on this selection are selected.{" "}
              <button
                type="button"
                onClick={selectAllMatching}
                className="font-semibold underline decoration-indigo-400 underline-offset-2 hover:text-indigo-700"
              >
                Select all {total.toLocaleString()} matching documents
              </button>
            </div>
          )}

        {selection.mode === "allMatching" && (
          <div className="border-t border-indigo-100 bg-indigo-50 px-4 py-3 text-center text-sm text-indigo-950">
            All {selectedCount.toLocaleString()} matching documents are selected.
          </div>
        )}

        <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3">
          <p className="text-sm text-slate-600">
            {total.toLocaleString()} document{total === 1 ? "" : "s"}
          </p>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page === 1 || loading}
              className="rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>
            <span className="text-sm text-slate-600">
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              onClick={() =>
                setPage((current) => Math.min(totalPages, current + 1))
              }
              disabled={page === totalPages || loading}
              className="rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
```

The `allMatching` selection mode avoids sending thousands of IDs: the server receives the active filters plus only IDs explicitly excluded by the user.