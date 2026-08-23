```tsx
import { useEffect, useMemo, useRef, useState } from "react";

const PAGE_SIZE = 50;

export type Document = {
  id: string;
  title: string;
  updatedAt: string;
  ownerName: string;
};

export type DocumentFilter = {
  search?: string;
  ownerId?: string;
  status?: "active" | "archived";
};

export type DocumentPage = {
  items: Document[];
  page: number; // 1-based
  total: number; // Total documents matching filter
};

type ExplicitSelection = {
  mode: "ids";
  scopeKey: string;
  ids: Set<string>;
};

type AllMatchingSelection = {
  mode: "all-matching";
  scopeKey: string;
  filter: DocumentFilter;
  excludedIds: Set<string>;
};

type Selection = ExplicitSelection | AllMatchingSelection;
type BulkAction = "archive" | "delete";

type DocumentsTableProps = {
  page: DocumentPage;
  filter: DocumentFilter;
  onPageChange: (page: number) => void;
  refresh: () => Promise<void>;
};

function emptySelection(scopeKey: string): ExplicitSelection {
  return { mode: "ids", scopeKey, ids: new Set() };
}

function selectionCount(selection: Selection, total: number) {
  return selection.mode === "ids"
    ? selection.ids.size
    : Math.max(0, total - selection.excludedIds.size);
}

function isSelected(selection: Selection, id: string) {
  return selection.mode === "ids"
    ? selection.ids.has(id)
    : !selection.excludedIds.has(id);
}

function selectionPayload(selection: Selection) {
  if (selection.mode === "ids") {
    return {
      kind: "ids" as const,
      ids: [...selection.ids],
    };
  }

  return {
    kind: "matching-filter" as const,
    filter: selection.filter,
    excludedIds: [...selection.excludedIds],
  };
}

/*
  Expected server contract:

  POST /api/documents/bulk/archive
  POST /api/documents/bulk/delete

  {
    selection:
      | { kind: "ids", ids: string[] }
      | {
          kind: "matching-filter",
          filter: DocumentFilter,
          excludedIds: string[]
        }
  }

  The server must evaluate matching-filter selections server-side. This avoids
  sending thousands of document IDs when the user selects every matching result.
*/
async function mutateDocuments(
  action: BulkAction,
  selection: Selection,
): Promise<{ affected: number }> {
  const response = await fetch(`/api/documents/bulk/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selection: selectionPayload(selection) }),
  });

  const body = (await response.json().catch(() => null)) as
    | { affected?: number; error?: string }
    | null;

  if (!response.ok) {
    throw new Error(body?.error ?? `Could not ${action} documents.`);
  }

  return { affected: body?.affected ?? 0 };
}

function TableCheckbox({
  checked,
  indeterminate = false,
  disabled = false,
  label,
  onChange,
}: {
  checked: boolean;
  indeterminate?: boolean;
  disabled?: boolean;
  label: string;
  onChange: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (inputRef.current) inputRef.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return (
    <input
      ref={inputRef}
      type="checkbox"
      checked={checked}
      disabled={disabled}
      aria-label={label}
      onChange={onChange}
      className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
    />
  );
}

export function DocumentsTable({
  page,
  filter,
  onPageChange,
  refresh,
}: DocumentsTableProps) {
  // This intentionally excludes page number, so selections persist across pages.
  const scopeKey = useMemo(() => JSON.stringify(filter), [filter]);
  const [selection, setSelection] = useState<Selection>(() =>
    emptySelection(scopeKey),
  );
  const [pendingAction, setPendingAction] = useState<BulkAction | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  // A changed search/filter represents a different result set, so clear selection.
  useEffect(() => {
    setSelection(emptySelection(scopeKey));
    setNotice("");
    setError("");
  }, [scopeKey]);

  const selectedCount = selectionCount(selection, page.total);
  const pageRowsSelected =
    page.items.length > 0 &&
    page.items.every((document) => isSelected(selection, document.id));
  const somePageRowsSelected =
    !pageRowsSelected &&
    page.items.some((document) => isSelected(selection, document.id));
  const pending = pendingAction !== null;
  const totalPages = Math.max(1, Math.ceil(page.total / PAGE_SIZE));

  function toggleDocument(id: string) {
    setSelection((current) => {
      if (current.scopeKey !== scopeKey) return emptySelection(scopeKey);

      if (current.mode === "ids") {
        const ids = new Set(current.ids);
        ids.has(id) ? ids.delete(id) : ids.add(id);
        return { ...current, ids };
      }

      const excludedIds = new Set(current.excludedIds);
      excludedIds.has(id) ? excludedIds.delete(id) : excludedIds.add(id);
      return { ...current, excludedIds };
    });
  }

  function toggleCurrentPage() {
    setSelection((current) => {
      if (current.scopeKey !== scopeKey) return emptySelection(scopeKey);

      if (current.mode === "ids") {
        const ids = new Set(current.ids);

        for (const document of page.items) {
          pageRowsSelected ? ids.delete(document.id) : ids.add(document.id);
        }

        return { ...current, ids };
      }

      const excludedIds = new Set(current.excludedIds);

      for (const document of page.items) {
        pageRowsSelected
          ? excludedIds.add(document.id)
          : excludedIds.delete(document.id);
      }

      return { ...current, excludedIds };
    });
  }

  function selectAllMatching() {
    setSelection({
      mode: "all-matching",
      scopeKey,
      filter: { ...filter },
      excludedIds: new Set(),
    });
  }

  async function runBulkAction(action: BulkAction) {
    if (selectedCount === 0 || pending) return;

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

    setPendingAction(action);
    setError("");
    setNotice("");

    try {
      const result = await mutateDocuments(action, selection);
      const affected = result.affected || selectedCount;

      setSelection(emptySelection(scopeKey));
      setNotice(
        `${action === "archive" ? "Archived" : "Deleted"} ${affected.toLocaleString()} document${
          affected === 1 ? "" : "s"
        }.`,
      );
      await refresh();
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : "Something went wrong. Please try again.",
      );
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <section className="space-y-4">
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th className="w-12 px-4 py-3 text-left">
                  <TableCheckbox
                    checked={pageRowsSelected}
                    indeterminate={somePageRowsSelected}
                    disabled={pending || page.items.length === 0}
                    label="Select all documents on this page"
                    onChange={toggleCurrentPage}
                  />
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Document
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
                <tr
                  key={document.id}
                  className={
                    isSelected(selection, document.id)
                      ? "bg-indigo-50/60"
                      : "hover:bg-slate-50"
                  }
                >
                  <td className="px-4 py-4">
                    <TableCheckbox
                      checked={isSelected(selection, document.id)}
                      disabled={pending}
                      label={`Select ${document.title}`}
                      onChange={() => toggleDocument(document.id)}
                    />
                  </td>
                  <td className="px-4 py-4 font-medium text-slate-900">
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
              ))}

              {page.items.length === 0 && (
                <tr>
                  <td
                    colSpan={4}
                    className="px-4 py-12 text-center text-sm text-slate-500"
                  >
                    No documents match this filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3">
          <p className="text-sm text-slate-600">
            {page.total.toLocaleString()} matching document
            {page.total === 1 ? "" : "s"}
          </p>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={pending || page.page <= 1}
              onClick={() => onPageChange(page.page - 1)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-sm text-slate-600">
              Page {page.page} of {totalPages}
            </span>
            <button
              type="button"
              disabled={pending || page.page >= totalPages}
              onClick={() => onPageChange(page.page + 1)}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {selectedCount > 0 && (
        <div
          aria-live="polite"
          className="sticky bottom-4 flex flex-col gap-3 rounded-xl border border-indigo-200 bg-white p-4 shadow-lg sm:flex-row sm:items-center sm:justify-between"
        >
          <div>
            <p className="font-semibold text-slate-900">
              {selectedCount.toLocaleString()} document
              {selectedCount === 1 ? "" : "s"} selected
            </p>

            {selection.mode === "ids" &&
              pageRowsSelected &&
              page.total > page.items.length && (
                <button
                  type="button"
                  disabled={pending}
                  onClick={selectAllMatching}
                  className="mt-1 text-sm font-medium text-indigo-700 hover:text-indigo-800 hover:underline disabled:opacity-50"
                >
                  Select all {page.total.toLocaleString()} matching documents
                </button>
              )}

            {selection.mode === "all-matching" && (
              <p className="mt-1 text-sm text-slate-600">
                All matching documents are selected. Unchecking a row excludes
                it.
              </p>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={pending}
              onClick={() => setSelection(emptySelection(scopeKey))}
              className="rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:opacity-50"
            >
              Clear
            </button>
            <button
              type="button"
              disabled={pending}
              onClick={() => runBulkAction("archive")}
              className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {pendingAction === "archive" ? "Archiving…" : "Archive"}
            </button>
            <button
              type="button"
              disabled={pending}
              onClick={() => runBulkAction("delete")}
              className="rounded-md bg-red-600 px-3 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {pendingAction === "delete" ? "Deleting…" : "Delete"}
            </button>
          </div>
        </div>
      )}

      {(notice || error) && (
        <p
          role={error ? "alert" : "status"}
          className={error ? "text-sm text-red-700" : "text-sm text-emerald-700"}
        >
          {error || notice}
        </p>
      )}
    </section>
  );
}
```