Here's a complete bulk-actions bar component with table, selection management, and mutation handling:

```tsx
import React, { useState, useCallback } from 'react';
import { Trash2, Archive, ChevronLeft, ChevronRight, AlertCircle } from 'lucide-react';

interface Document {
  id: string;
  title: string;
  updatedAt: string;
  ownerName: string;
}

interface PaginatedResponse {
  documents: Document[];
  total: number;
  page: number;
  pageSize: number;
}

// Mock API calls — replace with your mutation layer (tRPC, GraphQL, etc.)
async function archiveDocuments(ids: string[]): Promise<void> {
  const response = await fetch('/api/documents/archive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) throw new Error('Failed to archive documents');
}

async function deleteDocuments(ids: string[]): Promise<void> {
  const response = await fetch('/api/documents/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) throw new Error('Failed to delete documents');
}

async function fetchDocuments(page: number, pageSize: number = 50): Promise<PaginatedResponse> {
  const response = await fetch(`/api/documents?page=${page}&pageSize=${pageSize}`);
  if (!response.ok) throw new Error('Failed to fetch documents');
  return response.json();
}

export default function DocumentsTable() {
  const [page, setPage] = useState(1);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [data, setData] = useState<PaginatedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionInProgress, setActionInProgress] = useState<'archive' | 'delete' | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState(false);

  // Fetch documents on mount and page change
  React.useEffect(() => {
    setLoading(true);
    setError(null);
    setSelectedIds(new Set());
    
    fetchDocuments(page)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [page]);

  const toggleRow = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (!data?.documents) return;
    
    if (selectedIds.size === data.documents.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(data.documents.map((d) => d.id)));
    }
  }, [data, selectedIds.size]);

  const handleArchive = useCallback(async () => {
    setActionInProgress('archive');
    try {
      await archiveDocuments(Array.from(selectedIds));
      setSelectedIds(new Set());
      const fresh = await fetchDocuments(page);
      setData(fresh);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Archive failed');
    } finally {
      setActionInProgress(null);
    }
  }, [selectedIds, page]);

  const handleDelete = useCallback(async () => {
    setDeleteConfirm(false);
    setActionInProgress('delete');
    try {
      await deleteDocuments(Array.from(selectedIds));
      setSelectedIds(new Set());
      const fresh = await fetchDocuments(page);
      // If page is now empty and we're past page 1, go back
      if (fresh.documents.length === 0 && page > 1) {
        setPage(page - 1);
      } else {
        setData(fresh);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setActionInProgress(null);
    }
  }, [selectedIds, page]);

  if (error && !selectedIds.size) {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-800 flex items-center gap-2">
        <AlertCircle size={20} />
        <span>{error}</span>
      </div>
    );
  }

  const isAllSelected = data && selectedIds.size === data.documents.length && selectedIds.size > 0;
  const isEmpty = data && data.documents.length === 0;
  const totalPages = data ? Math.ceil(data.total / 50) : 0;

  return (
    <div className="flex flex-col gap-4">
      {/* Bulk Actions Bar */}
      {selectedIds.size > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 sticky top-0 z-20">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-blue-900">
                {selectedIds.size} selected
              </span>
              {data && selectedIds.size < data.total && (
                <span className="text-xs text-blue-700">of {data.total} total</span>
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleArchive}
                disabled={actionInProgress !== null}
                className="flex items-center gap-2 px-3 py-2 bg-white border border-blue-300 text-blue-900 rounded hover:bg-blue-50 disabled:opacity-50 text-sm font-medium"
              >
                {actionInProgress === 'archive' && (
                  <div className="w-4 h-4 border-2 border-blue-300 border-t-blue-600 rounded-full animate-spin" />
                )}
                {actionInProgress !== 'archive' && <Archive size={16} />}
                Archive
              </button>

              <button
                onClick={() => setDeleteConfirm(true)}
                disabled={actionInProgress !== null}
                className="flex items-center gap-2 px-3 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 text-sm font-medium"
              >
                {actionInProgress === 'delete' && (
                  <div className="w-4 h-4 border-2 border-white border-t-red-300 rounded-full animate-spin" />
                )}
                {actionInProgress !== 'delete' && <Trash2 size={16} />}
                Delete
              </button>
            </div>
          </div>

          {/* Delete Confirmation Inline */}
          {deleteConfirm && (
            <div className="mt-4 p-3 bg-red-100 border border-red-300 rounded">
              <p className="text-sm text-red-900 mb-3">
                Permanently delete {selectedIds.size} document{selectedIds.size !== 1 ? 's' : ''}? This cannot be undone.
              </p>
              <div className="flex gap-2 justify-end">
                <button
                  onClick={() => setDeleteConfirm(false)}
                  className="px-3 py-1 text-sm bg-white border border-red-300 text-red-900 rounded hover:bg-red-50"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  className="px-3 py-1 text-sm bg-red-600 text-white rounded hover:bg-red-700"
                >
                  Confirm Delete
                </button>
              </div>
            </div>
          )}

          {error && (
            <div className="mt-3 text-sm text-red-700">
              {error}
            </div>
          )}
        </div>
      )}

      {/* Table */}
      <div className="border rounded-lg overflow-hidden bg-white">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-4 py-3 w-12">
                <input
                  type="checkbox"
                  checked={isAllSelected}
                  onChange={toggleSelectAll}
                  disabled={isEmpty}
                  className="rounded"
                  aria-label="Select all on this page"
                />
              </th>
              <th className="px-4 py-3 text-left font-semibold text-gray-900">Title</th>
              <th className="px-4 py-3 text-left font-semibold text-gray-900 w-32">Owner</th>
              <th className="px-4 py-3 text-left font-semibold text-gray-900 w-28">Updated</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-500">
                  Loading...
                </td>
              </tr>
            ) : isEmpty ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-gray-500">
                  No documents
                </td>
              </tr>
            ) : (
              data?.documents.map((doc) => {
                const isSelected = selectedIds.has(doc.id);
                return (
                  <tr
                    key={doc.id}
                    className={`border-b hover:bg-gray-50 transition ${
                      isSelected ? 'bg-blue-50' : ''
                    }`}
                  >
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleRow(doc.id)}
                        className="rounded"
                      />
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900 truncate">
                      {doc.title}
                    </td>
                    <td className="px-4 py-3 text-gray-600">{doc.ownerName}</td>
                    <td className="px-4 py-3 text-gray-600">
                      {new Date(doc.updatedAt).toLocaleDateString()}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {!isEmpty && data && totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <div className="text-gray-600">
            Page {page} of {totalPages} • {data.total} total
          </div>

          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1}
              className="flex items-center gap-1 px-3 py-2 border rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ChevronLeft size={16} />
              Previous
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              className="flex items-center gap-1 px-3 py-2 border rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

**Key features:**

- **Selection state:** `Set<string>` for O(1) lookups on large doc counts
- **Bulk actions bar:** Sticky, appears only when rows selected, shows count and total
- **Select all:** Per-page checkbox toggles all 50 visible rows
- **Archive & Delete:** Separate mutations with loading spinners and error handling
- **Delete confirmation:** Inline modal prevents accidental deletions
- **Pagination:** 50 rows per page, handles thousands via fetch-on-change
- **UX polish:** Selected rows highlight in blue, hover states, disabled states during mutations
- **Error resilience:** Recovers page if last row deleted, refetches after mutation

Replace the fetch URLs and mutation functions with your actual API/tRPC/GraphQL layer.