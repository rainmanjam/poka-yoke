Here's a complete React component with state management and mutation handling for a bulk-actions bar on a documents table:

```tsx
import React, { useState, useCallback, useMemo } from 'react';
import { ChevronLeft, ChevronRight, Archive, Trash2, AlertCircle } from 'lucide-react';

interface Document {
  id: string;
  title: string;
  updatedAt: string;
  ownerName: string;
}

interface BulkActionsTableProps {
  totalCount: number;
  onFetchPage: (page: number, pageSize: number) => Promise<Document[]>;
}

const BulkActionsTable: React.FC<BulkActionsTableProps> = ({ totalCount, onFetchPage }) => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [currentPage, setCurrentPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);

  const pageSize = 50;
  const totalPages = Math.ceil(totalCount / pageSize);

  // Fetch documents for current page
  const loadPage = useCallback(async (page: number) => {
    setIsLoading(true);
    try {
      const data = await onFetchPage(page, pageSize);
      setDocuments(data);
      setSelectedIds(new Set()); // Clear selections on page change
    } catch (err) {
      setFeedbackMessage({ type: 'error', text: 'Failed to load documents' });
    } finally {
      setIsLoading(false);
    }
  }, [onFetchPage, pageSize]);

  // Load initial page
  React.useEffect(() => {
    loadPage(currentPage);
  }, [currentPage, loadPage]);

  const handleSelectAll = useCallback(() => {
    if (selectedIds.size === documents.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(documents.map(d => d.id)));
    }
  }, [documents, selectedIds]);

  const handleSelectOne = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleArchive = useCallback(async () => {
    if (selectedIds.size === 0) return;
    
    setIsMutating(true);
    try {
      // Mock mutation - replace with actual API call
      await archiveDocuments(Array.from(selectedIds));
      setFeedbackMessage({
        type: 'success',
        text: `Archived ${selectedIds.size} document${selectedIds.size !== 1 ? 's' : ''}`,
      });
      setSelectedIds(new Set());
      await loadPage(currentPage);
    } catch (err) {
      setFeedbackMessage({
        type: 'error',
        text: 'Failed to archive documents',
      });
    } finally {
      setIsMutating(false);
    }
  }, [selectedIds, currentPage, loadPage]);

  const handleDelete = useCallback(async () => {
    if (selectedIds.size === 0) return;
    
    if (!window.confirm(
      `Delete ${selectedIds.size} document${selectedIds.size !== 1 ? 's' : ''}? This cannot be undone.`
    )) {
      return;
    }

    setIsMutating(true);
    try {
      // Mock mutation - replace with actual API call
      await deleteDocuments(Array.from(selectedIds));
      setFeedbackMessage({
        type: 'success',
        text: `Deleted ${selectedIds.size} document${selectedIds.size !== 1 ? 's' : ''}`,
      });
      setSelectedIds(new Set());
      await loadPage(currentPage);
    } catch (err) {
      setFeedbackMessage({
        type: 'error',
        text: 'Failed to delete documents',
      });
    } finally {
      setIsMutating(false);
    }
  }, [selectedIds, currentPage, loadPage]);

  const allSelected = documents.length > 0 && selectedIds.size === documents.length;
  const someSelected = selectedIds.size > 0 && selectedIds.size < documents.length;

  // Clear feedback message after 4 seconds
  React.useEffect(() => {
    if (feedbackMessage) {
      const timer = setTimeout(() => setFeedbackMessage(null), 4000);
      return () => clearTimeout(timer);
    }
  }, [feedbackMessage]);

  return (
    <div className="w-full space-y-4">
      {/* Feedback Message */}
      {feedbackMessage && (
        <div
          className={`flex items-center gap-3 px-4 py-3 rounded-lg ${
            feedbackMessage.type === 'success'
              ? 'bg-green-50 text-green-800'
              : 'bg-red-50 text-red-800'
          }`}
        >
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span className="text-sm font-medium">{feedbackMessage.text}</span>
        </div>
      )}

      {/* Bulk Actions Bar */}
      {selectedIds.size > 0 && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={handleSelectAll}
              indeterminate={someSelected}
              className="w-4 h-4 rounded border-gray-300"
            />
            <span className="text-sm font-medium text-gray-900">
              {selectedIds.size} selected
              {totalCount > pageSize && ` of ${totalCount} total`}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleArchive}
              disabled={isMutating}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-white border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Archive className="w-4 h-4" />
              Archive
            </button>
            <button
              onClick={handleDelete}
              disabled={isMutating}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-white border border-red-300 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Trash2 className="w-4 h-4" />
              Delete
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="border rounded-lg overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-6 py-3 text-left">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={handleSelectAll}
                  indeterminate={someSelected}
                  className="w-4 h-4 rounded border-gray-300"
                />
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">
                Title
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">
                Owner
              </th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wide">
                Updated
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {isLoading ? (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-gray-500">
                  Loading...
                </td>
              </tr>
            ) : documents.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-6 py-8 text-center text-gray-500">
                  No documents found
                </td>
              </tr>
            ) : (
              documents.map(doc => (
                <tr key={doc.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(doc.id)}
                      onChange={() => handleSelectOne(doc.id)}
                      className="w-4 h-4 rounded border-gray-300"
                    />
                  </td>
                  <td className="px-6 py-4 text-sm font-medium text-gray-900">
                    {doc.title}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">
                    {doc.ownerName}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-600">
                    {new Date(doc.updatedAt).toLocaleDateString()}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-600">
          Showing {documents.length > 0 ? (currentPage - 1) * pageSize + 1 : 0} to{' '}
          {Math.min(currentPage * pageSize, totalCount)} of {totalCount}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
            Previous
          </button>
          <div className="flex items-center gap-1">
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const page = i + 1;
              return (
                <button
                  key={page}
                  onClick={() => setCurrentPage(page)}
                  className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    page === currentPage
                      ? 'bg-blue-600 text-white'
                      : 'border border-gray-300 text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  {page}
                </button>
              );
            })}
            {totalPages > 5 && <span className="px-2 py-2 text-gray-600">...</span>}
          </div>
          <button
            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-300 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Next
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};

// Mock mutation functions - replace with your actual API calls
async function archiveDocuments(ids: string[]): Promise<void> {
  // Replace with actual mutation:
  // return fetch('/api/documents/archive', {
  //   method: 'POST',
  //   headers: { 'Content-Type': 'application/json' },
  //   body: JSON.stringify({ ids }),
  // }).then(r => r.ok ? r.json() : Promise.reject(r.statusText));
  
  return new Promise(resolve => {
    setTimeout(resolve, 800);
    console.log('Archived:', ids);
  });
}

async function deleteDocuments(ids: string[]): Promise<void> {
  // Replace with actual mutation:
  // return fetch('/api/documents', {
  //   method: 'DELETE',
  //   headers: { 'Content-Type': 'application/json' },
  //   body: JSON.stringify({ ids }),
  // }).then(r => r.ok ? r.json() : Promise.reject(r.statusText));
  
  return new Promise(resolve => {
    setTimeout(resolve, 800);
    console.log('Deleted:', ids);
  });
}

export default BulkActionsTable;
```

**Key features:**

- **Selection state**: `Set<string>` for O(1) lookup when toggling individual selections
- **Select all/partial**: Shows indeterminate state when some rows selected
- **Bulk actions bar**: Appears when selections exist, positioned to show selected count and scale info
- **Pagination**: 50-row pages with navigation controls; selections clear on page change (standard UX)
- **Mutations**: Archive and Delete with loading states, confirmation on delete, error/success feedback
- **Accessibility**: Proper checkbox indeterminate states, disabled button states during mutations
- **Feedback messages**: Auto-dismiss after 4 seconds, color-coded success/error

Replace `archiveDocuments` and `deleteDocuments` with actual API calls. The component accepts `totalCount` and `onFetchPage` callback to handle data loading, making it agnostic to your backend.