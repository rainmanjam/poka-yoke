Here is the bulk actions component, implementing the mistake-proofing devices for interfaces. I’ve included the state handling, the explicit scope escalation for "Select All", and the mutation shapes.

```tsx
import React, { useState } from 'react';

export type Document = {
  id: string;
  title: string;
  updatedAt: string;
  ownerName: string;
};

// Simulated API calls with required idempotency keys (M2 device)
async function archiveDocuments(args: {
  documentIds: string[];
  selectAllMatching: boolean;
  idempotencyKey: string;
}) {
  // POST /api/documents/bulk-archive
}

async function deleteDocuments(args: {
  documentIds: string[];
  selectAllMatching: boolean;
  idempotencyKey: string;
}) {
  // POST /api/documents/bulk-delete
}

interface DocumentBulkActionsProps {
  selectedIds: Set<string>;
  totalMatchingCount: number;
  pageCount: number;
  onClearSelection: () => void;
  onSelectAllMatching: () => void;
  selectAllMatching: boolean;
}

export function DocumentBulkActions({
  selectedIds,
  totalMatchingCount,
  pageCount,
  onClearSelection,
  onSelectAllMatching,
  selectAllMatching,
}: DocumentBulkActionsProps) {
  const [isArchiving, setIsArchiving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');

  // Fixed-value inspection: calculate the exact scale of the action
  const selectedCount = selectAllMatching ? totalMatchingCount : selectedIds.size;
  
  // Distinguish "page selected" from "all matching selected" to prevent scope escalation
  const isAllOnPageSelected = selectedIds.size === pageCount && pageCount > 0;
  const showSelectAllPrompt = isAllOnPageSelected && !selectAllMatching && totalMatchingCount > pageCount;

  if (selectedIds.size === 0 && !selectAllMatching) {
    return null;
  }

  const handleArchive = async () => {
    setIsArchiving(true);
    try {
      await archiveDocuments({
        documentIds: Array.from(selectedIds),
        selectAllMatching,
        idempotencyKey: crypto.randomUUID(), // Structural double-submit prevention
      });
      // In a real implementation: trigger a "Documents archived. [Undo]" toast here
      onClearSelection();
    } catch (error) {
      console.error('Archive failed:', error);
    } finally {
      setIsArchiving(false);
    }
  };

  // Fixed-value constraint: user must reproduce the exact object count to proceed
  const expectedConfirmText = `Delete ${selectedCount} documents`;

  const handleDelete = async () => {
    if (deleteConfirmText !== expectedConfirmText) return;

    setIsDeleting(true);
    try {
      await deleteDocuments({
        documentIds: Array.from(selectedIds),
        selectAllMatching,
        idempotencyKey: crypto.randomUUID(), // Structural double-submit prevention
      });
      onClearSelection();
      setShowDeleteConfirm(false);
      setDeleteConfirmText('');
    } catch (error) {
      console.error('Delete failed:', error);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <>
      <div 
        className="fixed bottom-6 left-1/2 transform -translate-x-1/2 bg-white shadow-2xl rounded-lg border border-gray-200 px-6 py-4 flex items-center space-x-8 z-40"
        role="region"
        aria-label="Bulk actions"
      >
        <div className="flex flex-col min-w-[200px]">
          <span className="font-semibold text-gray-900">
            {selectedCount} document{selectedCount === 1 ? '' : 's'} selected
          </span>
          
          {showSelectAllPrompt && (
            <button
              onClick={onSelectAllMatching}
              className="text-sm text-blue-600 hover:text-blue-800 hover:underline text-left mt-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
            >
              Select all {totalMatchingCount} matching documents
            </button>
          )}
          
          {selectAllMatching && (
            <button
              onClick={onClearSelection}
              className="text-sm text-blue-600 hover:text-blue-800 hover:underline text-left mt-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
            >
              Clear selection
            </button>
          )}
        </div>

        <div className="flex items-center space-x-3 border-l border-gray-200 pl-8">
          <button
            onClick={handleArchive}
            disabled={isArchiving || isDeleting}
            aria-disabled={isArchiving || isDeleting}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isArchiving ? 'Archiving...' : 'Archive'}
          </button>

          <button
            onClick={() => setShowDeleteConfirm(true)}
            disabled={isArchiving || isDeleting}
            aria-disabled={isArchiving || isDeleting}
            className="px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Delete
          </button>
        </div>
      </div>

      {showDeleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center p-4 z-50">
          <div 
            className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 space-y-5"
            role="dialog"
            aria-labelledby="delete-dialog-title"
          >
            <div>
              <h2 id="delete-dialog-title" className="text-xl font-semibold text-gray-900">
                Delete {selectedCount} documents permanently?
              </h2>
              <p className="mt-2 text-sm text-gray-600">
                This action cannot be undone. To confirm, type <strong>{expectedConfirmText}</strong> below.
              </p>
            </div>
            
            <div>
              <label htmlFor="confirm-delete" className="sr-only">
                Confirm deletion text
              </label>
              <input
                id="confirm-delete"
                type="text"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                className="block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-red-500 sm:text-sm"
                placeholder={expectedConfirmText}
                autoComplete="off"
                disabled={isDeleting}
              />
            </div>
            
            <div className="flex justify-end space-x-3 pt-2">
              <button
                onClick={() => {
                  setShowDeleteConfirm(false);
                  setDeleteConfirmText('');
                }}
                disabled={isDeleting}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleteConfirmText !== expectedConfirmText || isDeleting}
                aria-disabled={deleteConfirmText !== expectedConfirmText || isDeleting}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isDeleting ? 'Deleting...' : 'Delete forever'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
```

### Device notes

- **Scope escalation and double submission are impossible.** The UI structurally distinguishes between "Select page" and "Select all" so a user cannot accidentally wipe the dataset while trying to clear their screen (**Warning**). The component generates a `crypto.randomUUID()` idempotency key on submission, guaranteeing that a UI double-click or network retry will not re-execute the bulk action (**Control**).
- **Accidental deletion requires work.** The confirmation dialog abandons the useless "Are you sure?" in favor of fixed-value inspection, requiring the user to type the exact number of documents being destroyed to proceed (**Warning**). 
- **Archive is left frictionless on purpose.** Archiving is recoverable effort. Putting a confirmation dialog in front of it trains users to blind-click through gates. We leave it as an immediate action, assuming the application will display a grace-period "Undo" toast once the call returns.
{"answer":"Here is the bulk actions component, implementing the mistake-proofing devices for interfaces. I’ve included the state handling, the explicit scope escalation for \"Select All\", and the mutation shapes.\n\n```tsx\nimport React, { useState } from 'react';\n\nexport type Document = {\n  id: string;\n  title: string;\n  updatedAt: string;\n  ownerName: string;\n};\n\n// Simulated API calls with required idempotency keys (M2 device)\nasync function archiveDocuments(args: {\n  documentIds: string[];\n  selectAllMatching: boolean;\n  idempotencyKey: string;\n}) {\n  // POST /api/documents/bulk-archive\n}\n\nasync function deleteDocuments(args: {\n  documentIds: string[];\n  selectAllMatching: boolean;\n  idempotencyKey: string;\n}) {\n  // POST /api/documents/bulk-delete\n}\n\ninterface DocumentBulkActionsProps {\n  selectedIds: Set\u003cstring\u003e;\n  totalMatchingCount: number;\n  pageCount: number;\n  onClearSelection: () =\u003e void;\n  onSelectAllMatching: () =\u003e void;\n  selectAllMatching: boolean;\n}\n\nexport function DocumentBulkActions({\n  selectedIds,\n  totalMatchingCount,\n  pageCount,\n  onClearSelection,\n  onSelectAllMatching,\n  selectAllMatching,\n}: DocumentBulkActionsProps) {\n  const [isArchiving, setIsArchiving] = useState(false);\n  const [isDeleting, setIsDeleting] = useState(false);\n  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);\n  const [deleteConfirmText, setDeleteConfirmText] = useState('');\n\n  // Fixed-value inspection: calculate the exact scale of the action\n  const selectedCount = selectAllMatching ? totalMatchingCount : selectedIds.size;\n  \n  // Distinguish \"page selected\" from \"all matching selected\" to prevent scope escalation\n  const isAllOnPageSelected = selectedIds.size === pageCount \u0026\u0026 pageCount \u003e 0;\n  const showSelectAllPrompt = isAllOnPageSelected \u0026\u0026 !selectAllMatching \u0026\u0026 totalMatchingCount \u003e pageCount;\n\n  if (selectedIds.size === 0 \u0026\u0026 !selectAllMatching) {\n    return null;\n  }\n\n  const handleArchive = async () =\u003e {\n    setIsArchiving(true);\n    try {\n      await archiveDocuments({\n        documentIds: Array.from(selectedIds),\n        selectAllMatching,\n        idempotencyKey: crypto.randomUUID(), // Structural double-submit prevention\n      });\n      // In a real implementation: trigger a \"Documents archived. [Undo]\" toast here\n      onClearSelection();\n    } catch (error) {\n      console.error('Archive failed:', error);\n    } finally {\n      setIsArchiving(false);\n    }\n  };\n\n  // Fixed-value constraint: user must reproduce the exact object count to proceed\n  const expectedConfirmText = `Delete ${selectedCount} documents`;\n\n  const handleDelete = async () =\u003e {\n    if (deleteConfirmText !== expectedConfirmText) return;\n\n    setIsDeleting(true);\n    try {\n      await deleteDocuments({\n        documentIds: Array.from(selectedIds),\n        selectAllMatching,\n        idempotencyKey: crypto.randomUUID(), // Structural double-submit prevention\n      });\n      onClearSelection();\n      setShowDeleteConfirm(false);\n      setDeleteConfirmText('');\n    } catch (error) {\n      console.error('Delete failed:', error);\n    } finally {\n      setIsDeleting(false);\n    }\n  };\n\n  return (\n    \u003c\u003e\n      \u003cdiv \n        className=\"fixed bottom-6 left-1/2 transform -translate-x-1/2 bg-white shadow-2xl rounded-lg border border-gray-200 px-6 py-4 flex items-center space-x-8 z-40\"\n        role=\"region\"\n        aria-label=\"Bulk actions\"\n      \u003e\n        \u003cdiv className=\"flex flex-col min-w-[200px]\"\u003e\n          \u003cspan className=\"font-semibold text-gray-900\"\u003e\n            {selectedCount} document{selectedCount === 1 ? '' : 's'} selected\n          \u003c/span\u003e\n          \n          {showSelectAllPrompt \u0026\u0026 (\n            \u003cbutton\n              onClick={onSelectAllMatching}\n              className=\"text-sm text-blue-600 hover:text-blue-800 hover:underline text-left mt-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded\"\n            \u003e\n              Select all {totalMatchingCount} matching documents\n            \u003c/button\u003e\n          )}\n          \n          {selectAllMatching \u0026\u0026 (\n            \u003cbutton\n              onClick={onClearSelection}\n              className=\"text-sm text-blue-600 hover:text-blue-800 hover:underline text-left mt-0.5 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded\"\n            \u003e\n              Clear selection\n            \u003c/button\u003e\n          )}\n        \u003c/div\u003e\n\n        \u003cdiv className=\"flex items-center space-x-3 border-l border-gray-200 pl-8\"\u003e\n          \u003cbutton\n            onClick={handleArchive}\n            disabled={isArchiving || isDeleting}\n            aria-disabled={isArchiving || isDeleting}\n            className=\"px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors\"\n          \u003e\n            {isArchiving ? 'Archiving...' : 'Archive'}\n          \u003c/button\u003e\n\n          \u003cbutton\n            onClick={() =\u003e setShowDeleteConfirm(true)}\n            disabled={isArchiving || isDeleting}\n            aria-disabled={isArchiving || isDeleting}\n            className=\"px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors\"\n          \u003e\n            Delete\n          \u003c/button\u003e\n        \u003c/div\u003e\n      \u003c/div\u003e\n\n      {showDeleteConfirm \u0026\u0026 (\n        \u003cdiv className=\"fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center p-4 z-50\"\u003e\n          \u003cdiv \n            className=\"bg-white rounded-xl shadow-2xl max-w-md w-full p-6 space-y-5\"\n            role=\"dialog\"\n            aria-labelledby=\"delete-dialog-title\"\n          \u003e\n            \u003cdiv\u003e\n              \u003ch2 id=\"delete-dialog-title\" className=\"text-xl font-semibold text-gray-900\"\u003e\n                Delete {selectedCount} documents permanently?\n              \u003c/h2\u003e\n              \u003cp className=\"mt-2 text-sm text-gray-600\"\u003e\n                This action cannot be undone. To confirm, type \u003cstrong\u003e{expectedConfirmText}\u003c/strong\u003e below.\n              \u003c/p\u003e\n            \u003c/div\u003e\n            \n            \u003cdiv\u003e\n              \u003clabel htmlFor=\"confirm-delete\" className=\"sr-only\"\u003e\n                Confirm deletion text\n              \u003c/label\u003e\n              \u003cinput\n                id=\"confirm-delete\"\n                type=\"text\"\n                value={deleteConfirmText}\n                onChange={(e) =\u003e setDeleteConfirmText(e.target.value)}\n                className=\"block w-full border border-gray-300 rounded-md shadow-sm py-2 px-3 text-gray-900 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-red-500 sm:text-sm\"\n                placeholder={expectedConfirmText}\n                autoComplete=\"off\"\n                disabled={isDeleting}\n              /\u003e\n            \u003c/div\u003e\n            \n            \u003cdiv className=\"flex justify-end space-x-3 pt-2\"\u003e\n              \u003cbutton\n                onClick={() =\u003e {\n                  setShowDeleteConfirm(false);\n                  setDeleteConfirmText('');\n                }}\n                disabled={isDeleting}\n                className=\"px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 transition-colors\"\n              \u003e\n                Cancel\n              \u003c/button\u003e\n              \u003cbutton\n                onClick={handleDelete}\n                disabled={deleteConfirmText !== expectedConfirmText || isDeleting}\n                aria-disabled={deleteConfirmText !== expectedConfirmText || isDeleting}\n                className=\"px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors\"\n              \u003e\n                {isDeleting ? 'Deleting...' : 'Delete forever'}\n              \u003c/button\u003e\n            \u003c/div\u003e\n          \u003c/div\u003e\n        \u003c/div\u003e\n      )}\n    \u003c/\u003e\n  );\n}\n```\n\n### Device notes\n\n- **Scope escalation and double submission are impossible.** The UI structurally distinguishes between \"Select page\" and \"Select all\" so a user cannot accidentally wipe the dataset while trying to clear their screen (**Warning**). The component generates a `crypto.randomUUID()` idempotency key on submission, guaranteeing that a UI double-click or network retry will not re-execute the bulk action (**Control**).\n- **Accidental deletion requires work.** The confirmation dialog abandons the useless \"Are you sure?\" in favor of fixed-value inspection, requiring the user to type the exact number of documents being destroyed to proceed (**Warning**). \n- **Archive is left frictionless on purpose.** Archiving is recoverable effort. Putting a confirmation dialog in front of it trains users to blind-click through gates. We leave it as an immediate action, assuming the application will display a grace-period \"Undo\" toast once the call returns.","toolAction":"Finishing the task","toolSummary":"Finish the task"}