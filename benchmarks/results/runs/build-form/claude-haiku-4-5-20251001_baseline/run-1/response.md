I'll build a complete bulk-actions component with selection state, pagination, and mutation handlers.

```jsx
import React, { useState, useCallback, useMemo } from 'react';
import { Archive, Trash2, CheckSquare, Square, AlertCircle } from 'lucide-react';

// Hook for managing row selection across paginated data
const useBulkSelection = (items) => {
  const [selectedIds, setSelectedIds] = useState(new Set());

  const toggleRow = useCallback((id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const togglePage = useCallback((pageIds) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      const allOnPageSelected = pageIds.every((id) => next.has(id));

      if (allOnPageSelected) {
        pageIds.forEach((id) => next.delete(id));
      } else {
        pageIds.forEach((id) => next.add(id));
      }
      return next;
    });
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  const pageIds = items.map((item) => item.id);
  const allOnPageSelected = pageIds.length > 0 && pageIds.every((id) => selectedIds.has(id));
  const someOnPageSelected = pageIds.some((id) => selectedIds.has(id)) && !allOnPageSelected;

  return {
    selectedIds,
    toggleRow,
    togglePage,
    clearSelection,
    allOnPageSelected,
    someOnPageSelected,
    selectedCount: selectedIds.size,
  };
};

// Mutation functions
const archiveDocuments = async (ids) => {
  const response = await fetch('/api/documents/archive', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids: Array.from(ids) }),
  });
  if (!response.ok) throw new Error('Archive failed');
  return response.json();
};

const deleteDocuments = async (ids) => {
  const response = await fetch('/api/documents/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids: Array.from(ids) }),
  });
  if (!response.ok) throw new Error('Delete failed');
  return response.json();
};

// Bulk actions bar component
const BulkActionsBar = ({
  selectedCount,
  isLoading,
  onArchive,
  onDelete,
  onClear,
}) => {
  const [deleteConfirm, setDeleteConfirm] = useState(false);

  if (selectedCount === 0) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg">
      <div className="max-w-7xl mx-auto px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium text-gray-700">
              {selectedCount} document{selectedCount !== 1 ? 's' : ''} selected
            </span>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={onClear}
              disabled={isLoading}
              className="px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Clear
            </button>

            <button
              onClick={onArchive}
              disabled={isLoading}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Archive size={16} />
              Archive
            </button>

            {!deleteConfirm ? (
              <button
                onClick={() => setDeleteConfirm(true)}
                disabled={isLoading}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Trash2 size={16} />
                Delete
              </button>
            ) : (
              <div className="flex items-center gap-2 bg-red-50 border border-red-200 rounded-md px-3 py-2">
                <AlertCircle size={16} className="text-red-600" />
                <span className="text-sm text-red-800 font-medium">Delete permanently?</span>
                <button
                  onClick={onDelete}
                  disabled={isLoading}
                  className="ml-2 px-2 py-1 text-xs font-medium text-white bg-red-600 rounded hover:bg-red-700 disabled:opacity-50"
                >
                  Delete
                </button>
                <button
                  onClick={() => setDeleteConfirm(false)}
                  disabled={isLoading}
                  className="px-2 py-1 text-xs font-medium text-gray-700 hover:bg-red-100 rounded disabled:opacity-50"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

// Table row component
const DocumentRow = ({ document, isSelected, onToggle }) => {
  const formattedDate = new Date(document.updatedAt).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <tr className="border-b border-gray-200 hover:bg-gray-50">
      <td className="w-12 px-4 py-3">
        <button
          onClick={() => onToggle(document.id)}
          className="inline-flex items-center justify-center text-gray-400 hover:text-gray-600"
        >
          {isSelected ? (
            <CheckSquare size={20} className="text-blue-600" />
          ) : (
            <Square size={20} />
          )}
        </button>
      </td>
      <td className="px-4 py-3 text-sm font-medium text-gray-900">{document.title}</td>
      <td className="px-4 py-3 text-sm text-gray-700">{document.ownerName}</td>
      <td className="px-4 py-3 text-sm text-gray-500">{formattedDate}</td>
    </tr>
  );
};

// Main table component
const DocumentsTable = ({ 
  documents, 
  totalCount,
  currentPage,
  pageSize = 50,
  onPageChange,
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const {
    selectedIds,
    toggleRow,
    togglePage,
    clearSelection,
    allOnPageSelected,
    someOnPageSelected,
    selectedCount,
  } = useBulkSelection(documents);

  const handleArchive = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await archiveDocuments(selectedIds);
      clearSelection();
      // Refresh documents list (call parent's refetch or similar)
      onPageChange(currentPage);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [selectedIds, clearSelection, onPageChange, currentPage]);

  const handleDelete = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await deleteDocuments(selectedIds);
      clearSelection();
      onPageChange(currentPage);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [selectedIds, clearSelection, onPageChange, currentPage]);

  const totalPages = Math.ceil(totalCount / pageSize);

  return (
    <div className="flex flex-col h-full">
      {error && (
        <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-md text-red-800 text-sm">
          {error}
        </div>
      )}

      <div className="overflow-x-auto flex-1">
        <table className="w-full border-collapse">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="w-12 px-4 py-3 text-left">
                <button
                  onClick={() => togglePage(documents.map((d) => d.id))}
                  className="inline-flex items-center justify-center text-gray-400 hover:text-gray-600"
                >
                  {allOnPageSelected ? (
                    <CheckSquare size={20} className="text-blue-600" />
                  ) : someOnPageSelected ? (
                    <div className="w-5 h-5 border-2 border-blue-600 rounded bg-blue-50 flex items-center justify-center">
                      <div className="w-2 h-2 bg-blue-600 rounded-sm" />
                    </div>
                  ) : (
                    <Square size={20} />
                  )}
                </button>
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Title
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Owner
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider">
                Updated
              </th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <DocumentRow
                key={doc.id}
                document={doc}
                isSelected={selectedIds.has(doc.id)}
                onToggle={toggleRow}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination footer */}
      <div className="border-t border-gray-200 bg-white px-4 py-3 flex items-center justify-between">
        <div className="text-sm text-gray-700">
          Showing <span className="font-medium">{(currentPage - 1) * pageSize + 1}</span> to{' '}
          <span className="font-medium">
            {Math.min(currentPage * pageSize, totalCount)}
          </span>{' '}
          of <span className="font-medium">{totalCount}</span> documents
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage === 1}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <span className="px-3 py-2 text-sm text-gray-700">
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage === totalPages}
            className="px-3 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      </div>

      {/* Bulk actions bar */}
      <BulkActionsBar
        selectedCount={selectedCount}
        isLoading={isLoading}
        onArchive={handleArchive}
        onDelete={handleDelete}
        onClear={clearSelection}
      />
    </div>
  );
};

export default DocumentsTable;
```

**Key features:**

- **`useBulkSelection` hook**: Tracks selected row IDs independent of pagination, handles page-level select-all
- **Smart checkboxes**: Indeterminate state for "some selected" on page
- **Sticky bar**: `fixed bottom-0` that appears only when items are selected
- **Delete confirmation**: Inline confirmation to prevent accidents
- **Loading states**: Disable buttons during mutations
- **Error handling**: Display errors to user
- **Pagination**: Works with paginated data; selections persist across page changes
- **Accessible**: Keyboard-friendly buttons, clear labels

The component assumes parent provides `documents` array, `totalCount`, `currentPage`, and `onPageChange` callback. Adapt the API endpoints `/api/documents/archive` and `/api/documents/delete` to your backend.