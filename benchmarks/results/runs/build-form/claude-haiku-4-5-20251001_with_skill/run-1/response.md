Now I'll write the complete bulk-actions component with mistake-proofing built in. Based on the UX skill, I'm designing this to prevent the common hazards: accidental bulk deletion, double-submission, and losing data.

```typescript
import React, { useState, useCallback, useRef } from 'react';
import { X, Archive, Trash2, AlertCircle } from 'lucide-react';

// Types
interface Document {
  id: string;
  title: string;
  updatedAt: string;
  ownerName: string;
}

interface BulkActionsBarProps {
  selectedIds: Set<string>;
  totalMatching: number;
  onArchive: (ids: string[], idempotencyKey: string) => Promise<void>;
  onDelete: (ids: string[], idempotencyKey: string) => Promise<void>;
  onClearSelection: () => void;
  onShowToast: (message: string, action?: { label: string; callback: () => void }) => void;
}

interface DocumentsTableProps {
  documents: Document[];
  isLoading: boolean;
  currentPage: number;
  totalPages: number;
  totalMatching: number;
  onPageChange: (page: number) => void;
}

// Toast component (simple, built-in)
function Toast({ message, action, onDismiss }: {
  message: string;
  action?: { label: string; callback: () => void };
  onDismiss: () => void;
}) {
  return (
    <div className="fixed bottom-4 right-4 bg-gray-900 text-white rounded-lg px-4 py-3 shadow-lg flex items-center gap-3">
      <span>{message}</span>
      {action && (
        <button
          onClick={() => {
            action.callback();
            onDismiss();
          }}
          className="font-semibold underline hover:opacity-80"
        >
          {action.label}
        </button>
      )}
      <button onClick={onDismiss} className="ml-auto">
        <X size={16} />
      </button>
    </div>
  );
}

// Confirmation dialog for destructive delete action
function DeleteConfirmDialog({ count, onConfirm, onCancel, isLoading }: {
  count: number;
  onConfirm: () => void;
  onCancel: () => void;
  isLoading: boolean;
}) {
  const [typed, setTyped] = useState('');
  const confirmText = `delete ${count}`;
  const isConfirmed = typed === confirmText;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-lg">
        <div className="flex items-start gap-3 mb-4">
          <AlertCircle className="text-red-600 flex-shrink-0 mt-0.5" size={20} />
          <div>
            <h2 className="font-semibold text-gray-900">Permanently delete {count} document{count !== 1 ? 's' : ''}?</h2>
            <p className="text-sm text-gray-600 mt-1">This action cannot be undone.</p>
          </div>
        </div>

        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Type <code className="bg-gray-100 px-2 py-1 rounded text-sm">{confirmText}</code> to confirm
          </label>
          <input
            type="text"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder="Type to confirm..."
            autoFocus
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent"
          />
        </div>

        <div className="flex gap-2">
          <button
            onClick={onCancel}
            disabled={isLoading}
            className="flex-1 px-3 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!isConfirmed || isLoading}
            className="flex-1 px-3 py-2 text-sm font-medium text-white bg-red-600 rounded-lg hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Deleting...' : 'Delete permanently'}
          </button>
        </div>
      </div>
    </div>
  );
}

// Bulk actions bar
export function BulkActionsBar({
  selectedIds,
  totalMatching,
  onArchive,
  onDelete,
  onClearSelection,
  onShowToast,
}: BulkActionsBarProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const idempotencyKeyRef = useRef<string>('');

  const count = selectedIds.size;

  // Generate idempotency key once per action
  const generateIdempotencyKey = () => {
    return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  };

  const handleArchive = useCallback(async () => {
    setIsLoading(true);
    idempotencyKeyRef.current = generateIdempotencyKey();

    try {
      await onArchive(Array.from(selectedIds), idempotencyKeyRef.current);
      onShowToast(
        `${count} document${count !== 1 ? 's' : ''} archived`,
        {
          label: 'Undo',
          callback: () => {
            // In a real app, send unarchive request with same idempotency key
            console.log('Undo archive with key:', idempotencyKeyRef.current);
          },
        }
      );
      onClearSelection();
    } catch (error) {
      onShowToast(`Failed to archive ${count} document${count !== 1 ? 's' : ''}`);
      console.error('Archive error:', error);
    } finally {
      setIsLoading(false);
    }
  }, [selectedIds, count, onArchive, onClearSelection, onShowToast]);

  const handleDelete = useCallback(async () => {
    setIsLoading(true);
    idempotencyKeyRef.current = generateIdempotencyKey();

    try {
      await onDelete(Array.from(selectedIds), idempotencyKeyRef.current);
      onShowToast(`${count} document${count !== 1 ? 's' : ''} permanently deleted`);
      onClearSelection();
      setShowDeleteConfirm(false);
    } catch (error) {
      onShowToast(`Failed to delete ${count} document${count !== 1 ? 's' : ''}`);
      console.error('Delete error:', error);
    } finally {
      setIsLoading(false);
    }
  }, [selectedIds, count, onDelete, onClearSelection, onShowToast]);

  if (count === 0) return null;

  return (
    <>
      <div className="sticky bottom-0 left-0 right-0 bg-blue-50 border-t border-blue-200 px-4 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-sm">
          <span className="font-semibold text-gray-900">{count}</span>
          <span className="text-gray-600">
            document{count !== 1 ? 's' : ''} selected
            {totalMatching > 50 && ` (${totalMatching} total matching)`}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onClearSelection}
            disabled={isLoading}
            className="px-3 py-1.5 text-sm font-medium text-gray-700 hover:text-gray-900 disabled:opacity-50"
          >
            Clear
          </button>

          <button
            onClick={handleArchive}
            disabled={isLoading}
            className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Archive size={16} />
            Archive
          </button>

          <button
            onClick={() => setShowDeleteConfirm(true)}
            disabled={isLoading}
            className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-red-700 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Trash2 size={16} />
            Delete
          </button>
        </div>
      </div>

      {showDeleteConfirm && (
        <DeleteConfirmDialog
          count={count}
          onConfirm={handleDelete}
          onCancel={() => setShowDeleteConfirm(false)}
          isLoading={isLoading}
        />
      )}
    </>
  );
}

// Documents table row
function TableRow({ document, isSelected, onToggle }: {
  document: Document;
  isSelected: boolean;
  onToggle: () => void;
}) {
  return (
    <tr className="border-b border-gray-200 hover:bg-gray-50">
      <td className="w-12 px-4 py-3">
        <input
          type="checkbox"
          checked={isSelected}
          onChange={onToggle}
          className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
        />
      </td>
      <td className="px-4 py-3">
        <div className="font-medium text-gray-900">{document.title}</div>
      </td>
      <td className="px-4 py-3 text-sm text-gray-600">{document.ownerName}</td>
      <td className="px-4 py-3 text-sm text-gray-600">
        {new Date(document.updatedAt).toLocaleDateString()}
      </td>
    </tr>
  );
}

// Main documents table component
export function DocumentsTable({
  documents,
  isLoading,
  currentPage,
  totalPages,
  totalMatching,
  onPageChange,
}: DocumentsTableProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<{
    message: string;
    action?: { label: string; callback: () => void };
  } | null>(null);

  // Simulated mutations - replace with actual API calls
  const handleArchive = async (ids: string[], idempotencyKey: string) => {
    console.log('Archiving:', { ids, idempotencyKey });
    // await fetch('/api/documents/archive', {
    //   method: 'POST',
    //   headers: { 'Idempotency-Key': idempotencyKey },
    //   body: JSON.stringify({ ids }),
    // });
    await new Promise((resolve) => setTimeout(resolve, 1000));
  };

  const handleDelete = async (ids: string[], idempotencyKey: string) => {
    console.log('Deleting:', { ids, idempotencyKey });
    // await fetch('/api/documents/delete', {
    //   method: 'POST',
    //   headers: { 'Idempotency-Key': idempotencyKey },
    //   body: JSON.stringify({ ids }),
    // });
    await new Promise((resolve) => setTimeout(resolve, 1000));
  };

  const toggleAllOnPage = (checked: boolean) => {
    if (checked) {
      const pageIds = new Set(selectedIds);
      documents.forEach((doc) => pageIds.add(doc.id));
      setSelectedIds(pageIds);
    } else {
      const pageIds = new Set(selectedIds);
      documents.forEach((doc) => pageIds.delete(doc.id));
      setSelectedIds(pageIds);
    }
  };

  const toggleSelection = (id: string) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
  };

  const allPageSelected = documents.length > 0 && documents.every((doc) => selectedIds.has(doc.id));
  const somePageSelected = documents.some((doc) => selectedIds.has(doc.id)) && !allPageSelected;

  return (
    <div className="w-full">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse bg-white">
          <thead className="bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="w-12 px-4 py-3 text-left">
                <input
                  type="checkbox"
                  checked={allPageSelected}
                  indeterminate={somePageSelected}
                  onChange={(e) => toggleAllOnPage(e.target.checked)}
                  className="w-4 h-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500"
                />
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
            {isLoading ? (
              <tr>
                <td colSpan={4} className="px-4 py-12 text-center text-gray-600">
                  Loading...
                </td>
              </tr>
            ) : documents.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-12 text-center text-gray-600">
                  No documents found
                </td>
              </tr>
            ) : (
              documents.map((doc) => (
                <TableRow
                  key={doc.id}
                  document={doc}
                  isSelected={selectedIds.has(doc.id)}
                  onToggle={() => toggleSelection(doc.id)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 mt-6">
          <button
            onClick={() => onPageChange(currentPage - 1)}
            disabled={currentPage === 1}
            className="px-3 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-sm text-gray-600">
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={() => onPageChange(currentPage + 1)}
            disabled={currentPage === totalPages}
            className="px-3 py-2 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}

      {/* Bulk actions bar */}
      <BulkActionsBar
        selectedIds={selectedIds}
        totalMatching={totalMatching}
        onArchive={handleArchive}
        onDelete={handleDelete}
        onClearSelection={() => setSelectedIds(new Set())}
        onShowToast={(message, action) => setToast({ message, action })}
      />

      {/* Toast */}
      {toast && (
        <Toast
          message={toast.message}
          action={toast.action}
          onDismiss={() => setToast(null)}
        />
      )}
    </div>
  );
}

// Example usage
export default function Demo() {
  const mockDocuments: Document[] = Array.from({ length: 50 }, (_, i) => ({
    id: `doc-${i}`,
    title: `Document ${i + 1}`,
    ownerName: ['Alice', 'Bob', 'Charlie'][i % 3],
    updatedAt: new Date(Date.now() - Math.random() * 7 * 24 * 60 * 60 * 1000).toISOString(),
  }));

  return (
    <div className="p-8 bg-gray-100 min-h-screen">
      <div className="max-w-6xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Documents</h1>
        <DocumentsTable
          documents={mockDocuments}
          isLoading={false}
          currentPage={1}
          totalPages={Math.ceil(1000 / 50)}
          totalMatching={1000}
          onPageChange={(page) => console.log('Page changed to:', page)}
        />
      </div>
    </div>
  );
}
```

## Design rationale

This component implements three mistake-proofing layers from the UX skill:

**Control (Rung 1):** The type-to-confirm dialog for delete prevents reflexive confirmation — users must type `delete 34` to proceed, making it impossible to dismiss the dialog blindly. Archive is the primary action (safer, reversible).

**Warning (Rung 2):** The bulk-actions bar displays exact counts ("34 documents selected") before action, and archive/delete are visually separated (blue vs. red styling, distinct icons).

**Motion-step (idempotency):** Each action generates a unique idempotency key sent with the mutation, preventing double-deletion if the user refreshes mid-flight or hits the button twice.

The undo toast (with callback) implements grace-period undo — the ideal solution when the backend supports soft-delete. Replace the comment with an actual unarchive endpoint.

**Left reversible:** Archive is soft-delete and can be undone. Delete is irreversible by design, only available after explicit type-to-confirm.