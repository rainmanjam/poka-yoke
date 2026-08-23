Here is the complete React component fulfilling the requirements. 

Because the documents list can contain thousands of records across many pages, this solution uses an **explicit/implicit selection model** (similar to Gmail). 
- **Explicit selection**: Users check individual rows (e.g., storing a `Set` of IDs).
- **Implicit selection**: When a user selects all 50 on the current page, a banner appears allowing them to "Select all X matching documents." If they click it, the state flips to `implicitAll` mode. From then on, deselecting a row tracks **excluded IDs**.

When mutations (Archive/Delete) run, they pass this state model to the backend so the database query can properly handle `WHERE id IN (...)` vs `WHERE id NOT IN (...) AND filter_match = true`.

```tsx
import React, { useState, useMemo } from 'react';

// --- Types ---
interface Document {
  id: string;
  title: string;
  updatedAt: string;
  ownerName: string;
}

// Crucial for supporting bulk actions across thousands of paginated records
export type SelectionState =
  | { mode: 'explicit'; selectedIds: Set<string> }
  | { mode: 'implicitAll'; excludedIds: Set<string> };

// --- Mock Data & Mutations Hooks ---
const useDocuments = (page: number) => {
  const limit = 50;
  const totalCount = 2453;
  
  const data: Document[] = useMemo(() => 
    Array.from({ length: limit }).map((_, i) => ({
      id: `doc-${page}-${i}`,
      title: `Quarterly Report - Batch ${page * limit + i + 1}`,
      updatedAt: new Date(Date.now() - Math.random() * 10000000000).toISOString(),
      ownerName: 'Jane Doe',
    })), [page]
  );
  
  return { data, totalCount, isLoading: false };
};

const useDocumentMutations = () => {
  const archiveDocuments = async (selection: SelectionState) => {
    // Backend would receive this and either do:
    // WHERE id IN (selection.selectedIds) 
    // OR WHERE id NOT IN (selection.excludedIds) AND <current filters>
    console.log('Archiving', selection);
  };
  
  const deleteDocuments = async (selection: SelectionState) => {
    console.log('Deleting', selection);
  };
  
  return { archiveDocuments, deleteDocuments, isPending: false };
};

// --- Main Component ---
export default function DocumentTable() {
  const [page, setPage] = useState(1);
  const { data: documents, totalCount } = useDocuments(page);
  const { archiveDocuments, deleteDocuments, isPending } = useDocumentMutations();
  
  const [selection, setSelection] = useState<SelectionState>({ 
    mode: 'explicit', 
    selectedIds: new Set() 
  });

  // -- Selection Logic --
  const pageIds = documents.map(doc => doc.id);
  
  const isRowSelected = (id: string) => {
    if (selection.mode === 'implicitAll') return !selection.excludedIds.has(id);
    return selection.selectedIds.has(id);
  };

  const selectedCountOnPage = pageIds.filter(isRowSelected).length;
  const isAllPageSelected = pageIds.length > 0 && selectedCountOnPage === pageIds.length;
  const isSomePageSelected = selectedCountOnPage > 0 && selectedCountOnPage < pageIds.length;
  
  const totalSelectedCount = selection.mode === 'implicitAll' 
    ? totalCount - selection.excludedIds.size
    : selection.selectedIds.size;

  const showBulkBar = totalSelectedCount > 0;

  // -- Handlers --
  const toggleRow = (id: string) => {
    setSelection(prev => {
      if (prev.mode === 'implicitAll') {
        const next = new Set(prev.excludedIds);
        next.has(id) ? next.delete(id) : next.add(id);
        return { ...prev, excludedIds: next };
      } else {
        const next = new Set(prev.selectedIds);
        next.has(id) ? next.delete(id) : next.add(id);
        return { ...prev, selectedIds: next };
      }
    });
  };

  const togglePageSelection = () => {
    setSelection(prev => {
      if (prev.mode === 'implicitAll') {
        const next = new Set(prev.excludedIds);
        // If all are selected, exclude them. Otherwise, un-exclude them.
        pageIds.forEach(id => isAllPageSelected ? next.add(id) : next.delete(id));
        return { ...prev, excludedIds: next };
      } else {
        const next = new Set(prev.selectedIds);
        // If all are selected, unselect them. Otherwise, select them.
        pageIds.forEach(id => isAllPageSelected ? next.delete(id) : next.add(id));
        return { ...prev, selectedIds: next };
      }
    });
  };

  const selectAllMatching = () => {
    setSelection({ mode: 'implicitAll', excludedIds: new Set() });
  };

  const clearSelection = () => {
    setSelection({ mode: 'explicit', selectedIds: new Set() });
  };

  const handleAction = async (action: 'archive' | 'delete') => {
    if (action === 'archive') await archiveDocuments(selection);
    if (action === 'delete') await deleteDocuments(selection);
    clearSelection(); // Clear on success
  };

  return (
    <div className="relative min-h-screen bg-gray-100 p-8 text-sm">
      <div className="mx-auto max-w-5xl bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
        
        {/* Table Header Toolbar */}
        <div className="px-4 py-4 border-b border-gray-200 bg-white flex items-center justify-between">
          <h1 className="text-lg font-semibold text-gray-900">Company Documents</h1>
        </div>

        {/* Table */}
        <div className="overflow-x-auto relative">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50 text-gray-600">
                <th className="px-4 py-3 w-12 text-center">
                  <input
                    type="checkbox"
                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                    checked={isAllPageSelected}
                    ref={input => { if (input) input.indeterminate = isSomePageSelected; }}
                    onChange={togglePageSelection}
                  />
                </th>
                <th className="px-4 py-3 font-medium">Title</th>
                <th className="px-4 py-3 font-medium">Owner</th>
                <th className="px-4 py-3 font-medium">Last Modified</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {documents.map((doc) => {
                const selected = isRowSelected(doc.id);
                return (
                  <tr 
                    key={doc.id} 
                    className={`hover:bg-gray-50 transition-colors ${selected ? 'bg-blue-50/40' : ''}`}
                  >
                    <td className="px-4 py-3 text-center">
                      <input
                        type="checkbox"
                        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer"
                        checked={selected}
                        onChange={() => toggleRow(doc.id)}
                      />
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900">{doc.title}</td>
                    <td className="px-4 py-3 text-gray-500">{doc.ownerName}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {new Date(doc.updatedAt).toLocaleDateString()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Basic Pagination */}
        <div className="px-4 py-3 border-t border-gray-200 bg-gray-50 flex justify-between items-center text-gray-600">
          <div>
            Showing {(page - 1) * 50 + 1} to {Math.min(page * 50, totalCount)} of {totalCount} results
          </div>
          <div className="space-x-2">
            <button 
              disabled={page === 1} 
              onClick={() => setPage(p => p - 1)}
              className="px-3 py-1.5 border border-gray-300 rounded bg-white disabled:opacity-50 hover:bg-gray-50 transition-colors"
            >
              Previous
            </button>
            <button 
              disabled={page * 50 >= totalCount}
              onClick={() => setPage(p => p + 1)}
              className="px-3 py-1.5 border border-gray-300 rounded bg-white disabled:opacity-50 hover:bg-gray-50 transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {/* Floating Bulk Action Bar */}
      {showBulkBar && (
        <div className="fixed bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-3 z-50">
          
          {/* Select All Notice Banner */}
          {selection.mode === 'explicit' && totalSelectedCount === 50 && totalSelectedCount < totalCount && (
            <div className="bg-blue-50 border border-blue-100 text-blue-800 px-4 py-2 rounded-full shadow-md text-sm flex items-center gap-2">
              <span>All 50 documents on this page are selected.</span>
              <button 
                onClick={selectAllMatching}
                className="font-semibold underline hover:text-blue-900 focus:outline-none"
              >
                Select all {totalCount.toLocaleString()} matching documents
              </button>
            </div>
          )}

          {/* Action Dashboard */}
          <div className="bg-gray-900 text-white px-6 py-3.5 rounded-xl shadow-2xl flex items-center gap-6 border border-gray-800">
            
            {/* Count */}
            <div className="flex items-center gap-3">
              <span className="bg-blue-600 text-white font-medium px-2.5 py-0.5 rounded-full text-xs">
                {totalSelectedCount.toLocaleString()}
              </span>
              <span className="font-medium whitespace-nowrap text-sm">
                {totalSelectedCount === 1 ? 'Document' : 'Documents'} selected
              </span>
            </div>
            
            <div className="h-6 w-px bg-gray-700" />
            
            {/* Actions */}
            <div className="flex items-center gap-2">
              <button
                disabled={isPending}
                onClick={() => handleAction('archive')}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-gray-800 transition-colors focus:ring-2 focus:ring-gray-400 focus:outline-none disabled:opacity-50"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                </svg>
                Archive
              </button>
              
              <button
                disabled={isPending}
                onClick={() => handleAction('delete')}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium text-red-400 hover:bg-gray-800 hover:text-red-300 transition-colors focus:ring-2 focus:ring-red-400 focus:outline-none disabled:opacity-50"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                Delete
              </button>
            </div>

            <div className="h-6 w-px bg-gray-700" />
            
            {/* Close / Dismiss */}
            <button
              onClick={clearSelection}
              className="p-1 hover:bg-gray-800 rounded-full transition-colors focus:ring-2 focus:ring-gray-400 focus:outline-none"
              aria-label="Clear selection"
            >
              <svg className="w-5 h-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```
{"answer":"Here is the complete React component fulfilling the requirements. \n\nBecause the documents list can contain thousands of records across many pages, this solution uses an **explicit/implicit selection model** (similar to Gmail). \n- **Explicit selection**: Users check individual rows (e.g., storing a `Set` of IDs).\n- **Implicit selection**: When a user selects all 50 on the current page, a banner appears allowing them to \"Select all X matching documents.\" If they click it, the state flips to `implicitAll` mode. From then on, deselecting a row tracks **excluded IDs**.\n\nWhen mutations (Archive/Delete) run, they pass this state model to the backend so the database query can properly handle `WHERE id IN (...)` vs `WHERE id NOT IN (...) AND filter_match = true`.\n\n```tsx\nimport React, { useState, useMemo } from 'react';\n\n// --- Types ---\ninterface Document {\n  id: string;\n  title: string;\n  updatedAt: string;\n  ownerName: string;\n}\n\n// Crucial for supporting bulk actions across thousands of paginated records\nexport type SelectionState =\n  | { mode: 'explicit'; selectedIds: Set\u003cstring\u003e }\n  | { mode: 'implicitAll'; excludedIds: Set\u003cstring\u003e };\n\n// --- Mock Data \u0026 Mutations Hooks ---\nconst useDocuments = (page: number) =\u003e {\n  const limit = 50;\n  const totalCount = 2453;\n  \n  const data: Document[] = useMemo(() =\u003e \n    Array.from({ length: limit }).map((_, i) =\u003e ({\n      id: `doc-${page}-${i}`,\n      title: `Quarterly Report - Batch ${page * limit + i + 1}`,\n      updatedAt: new Date(Date.now() - Math.random() * 10000000000).toISOString(),\n      ownerName: 'Jane Doe',\n    })), [page]\n  );\n  \n  return { data, totalCount, isLoading: false };\n};\n\nconst useDocumentMutations = () =\u003e {\n  const archiveDocuments = async (selection: SelectionState) =\u003e {\n    // Backend would receive this and either do:\n    // WHERE id IN (selection.selectedIds) \n    // OR WHERE id NOT IN (selection.excludedIds) AND \u003ccurrent filters\u003e\n    console.log('Archiving', selection);\n  };\n  \n  const deleteDocuments = async (selection: SelectionState) =\u003e {\n    console.log('Deleting', selection);\n  };\n  \n  return { archiveDocuments, deleteDocuments, isPending: false };\n};\n\n// --- Main Component ---\nexport default function DocumentTable() {\n  const [page, setPage] = useState(1);\n  const { data: documents, totalCount } = useDocuments(page);\n  const { archiveDocuments, deleteDocuments, isPending } = useDocumentMutations();\n  \n  const [selection, setSelection] = useState\u003cSelectionState\u003e({ \n    mode: 'explicit', \n    selectedIds: new Set() \n  });\n\n  // -- Selection Logic --\n  const pageIds = documents.map(doc =\u003e doc.id);\n  \n  const isRowSelected = (id: string) =\u003e {\n    if (selection.mode === 'implicitAll') return !selection.excludedIds.has(id);\n    return selection.selectedIds.has(id);\n  };\n\n  const selectedCountOnPage = pageIds.filter(isRowSelected).length;\n  const isAllPageSelected = pageIds.length \u003e 0 \u0026\u0026 selectedCountOnPage === pageIds.length;\n  const isSomePageSelected = selectedCountOnPage \u003e 0 \u0026\u0026 selectedCountOnPage \u003c pageIds.length;\n  \n  const totalSelectedCount = selection.mode === 'implicitAll' \n    ? totalCount - selection.excludedIds.size\n    : selection.selectedIds.size;\n\n  const showBulkBar = totalSelectedCount \u003e 0;\n\n  // -- Handlers --\n  const toggleRow = (id: string) =\u003e {\n    setSelection(prev =\u003e {\n      if (prev.mode === 'implicitAll') {\n        const next = new Set(prev.excludedIds);\n        next.has(id) ? next.delete(id) : next.add(id);\n        return { ...prev, excludedIds: next };\n      } else {\n        const next = new Set(prev.selectedIds);\n        next.has(id) ? next.delete(id) : next.add(id);\n        return { ...prev, selectedIds: next };\n      }\n    });\n  };\n\n  const togglePageSelection = () =\u003e {\n    setSelection(prev =\u003e {\n      if (prev.mode === 'implicitAll') {\n        const next = new Set(prev.excludedIds);\n        // If all are selected, exclude them. Otherwise, un-exclude them.\n        pageIds.forEach(id =\u003e isAllPageSelected ? next.add(id) : next.delete(id));\n        return { ...prev, excludedIds: next };\n      } else {\n        const next = new Set(prev.selectedIds);\n        // If all are selected, unselect them. Otherwise, select them.\n        pageIds.forEach(id =\u003e isAllPageSelected ? next.delete(id) : next.add(id));\n        return { ...prev, selectedIds: next };\n      }\n    });\n  };\n\n  const selectAllMatching = () =\u003e {\n    setSelection({ mode: 'implicitAll', excludedIds: new Set() });\n  };\n\n  const clearSelection = () =\u003e {\n    setSelection({ mode: 'explicit', selectedIds: new Set() });\n  };\n\n  const handleAction = async (action: 'archive' | 'delete') =\u003e {\n    if (action === 'archive') await archiveDocuments(selection);\n    if (action === 'delete') await deleteDocuments(selection);\n    clearSelection(); // Clear on success\n  };\n\n  return (\n    \u003cdiv className=\"relative min-h-screen bg-gray-100 p-8 text-sm\"\u003e\n      \u003cdiv className=\"mx-auto max-w-5xl bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden\"\u003e\n        \n        {/* Table Header Toolbar */}\n        \u003cdiv className=\"px-4 py-4 border-b border-gray-200 bg-white flex items-center justify-between\"\u003e\n          \u003ch1 className=\"text-lg font-semibold text-gray-900\"\u003eCompany Documents\u003c/h1\u003e\n        \u003c/div\u003e\n\n        {/* Table */}\n        \u003cdiv className=\"overflow-x-auto relative\"\u003e\n          \u003ctable className=\"w-full text-left border-collapse\"\u003e\n            \u003cthead\u003e\n              \u003ctr className=\"border-b border-gray-200 bg-gray-50 text-gray-600\"\u003e\n                \u003cth className=\"px-4 py-3 w-12 text-center\"\u003e\n                  \u003cinput\n                    type=\"checkbox\"\n                    className=\"rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer\"\n                    checked={isAllPageSelected}\n                    ref={input =\u003e { if (input) input.indeterminate = isSomePageSelected; }}\n                    onChange={togglePageSelection}\n                  /\u003e\n                \u003c/th\u003e\n                \u003cth className=\"px-4 py-3 font-medium\"\u003eTitle\u003c/th\u003e\n                \u003cth className=\"px-4 py-3 font-medium\"\u003eOwner\u003c/th\u003e\n                \u003cth className=\"px-4 py-3 font-medium\"\u003eLast Modified\u003c/th\u003e\n              \u003c/tr\u003e\n            \u003c/thead\u003e\n            \u003ctbody className=\"divide-y divide-gray-100\"\u003e\n              {documents.map((doc) =\u003e {\n                const selected = isRowSelected(doc.id);\n                return (\n                  \u003ctr \n                    key={doc.id} \n                    className={`hover:bg-gray-50 transition-colors ${selected ? 'bg-blue-50/40' : ''}`}\n                  \u003e\n                    \u003ctd className=\"px-4 py-3 text-center\"\u003e\n                      \u003cinput\n                        type=\"checkbox\"\n                        className=\"rounded border-gray-300 text-blue-600 focus:ring-blue-500 cursor-pointer\"\n                        checked={selected}\n                        onChange={() =\u003e toggleRow(doc.id)}\n                      /\u003e\n                    \u003c/td\u003e\n                    \u003ctd className=\"px-4 py-3 font-medium text-gray-900\"\u003e{doc.title}\u003c/td\u003e\n                    \u003ctd className=\"px-4 py-3 text-gray-500\"\u003e{doc.ownerName}\u003c/td\u003e\n                    \u003ctd className=\"px-4 py-3 text-gray-500\"\u003e\n                      {new Date(doc.updatedAt).toLocaleDateString()}\n                    \u003c/td\u003e\n                  \u003c/tr\u003e\n                );\n              })}\n            \u003c/tbody\u003e\n          \u003c/table\u003e\n        \u003c/div\u003e\n\n        {/* Basic Pagination */}\n        \u003cdiv className=\"px-4 py-3 border-t border-gray-200 bg-gray-50 flex justify-between items-center text-gray-600\"\u003e\n          \u003cdiv\u003e\n            Showing {(page - 1) * 50 + 1} to {Math.min(page * 50, totalCount)} of {totalCount} results\n          \u003c/div\u003e\n          \u003cdiv className=\"space-x-2\"\u003e\n            \u003cbutton \n              disabled={page === 1} \n              onClick={() =\u003e setPage(p =\u003e p - 1)}\n              className=\"px-3 py-1.5 border border-gray-300 rounded bg-white disabled:opacity-50 hover:bg-gray-50 transition-colors\"\n            \u003e\n              Previous\n            \u003c/button\u003e\n            \u003cbutton \n              disabled={page * 50 \u003e= totalCount}\n              onClick={() =\u003e setPage(p =\u003e p + 1)}\n              className=\"px-3 py-1.5 border border-gray-300 rounded bg-white disabled:opacity-50 hover:bg-gray-50 transition-colors\"\n            \u003e\n              Next\n            \u003c/button\u003e\n          \u003c/div\u003e\n        \u003c/div\u003e\n      \u003c/div\u003e\n\n      {/* Floating Bulk Action Bar */}\n      {showBulkBar \u0026\u0026 (\n        \u003cdiv className=\"fixed bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-3 z-50\"\u003e\n          \n          {/* Select All Notice Banner */}\n          {selection.mode === 'explicit' \u0026\u0026 totalSelectedCount === 50 \u0026\u0026 totalSelectedCount \u003c totalCount \u0026\u0026 (\n            \u003cdiv className=\"bg-blue-50 border border-blue-100 text-blue-800 px-4 py-2 rounded-full shadow-md text-sm flex items-center gap-2\"\u003e\n              \u003cspan\u003eAll 50 documents on this page are selected.\u003c/span\u003e\n              \u003cbutton \n                onClick={selectAllMatching}\n                className=\"font-semibold underline hover:text-blue-900 focus:outline-none\"\n              \u003e\n                Select all {totalCount.toLocaleString()} matching documents\n              \u003c/button\u003e\n            \u003c/div\u003e\n          )}\n\n          {/* Action Dashboard */}\n          \u003cdiv className=\"bg-gray-900 text-white px-6 py-3.5 rounded-xl shadow-2xl flex items-center gap-6 border border-gray-800\"\u003e\n            \n            {/* Count */}\n            \u003cdiv className=\"flex items-center gap-3\"\u003e\n              \u003cspan className=\"bg-blue-600 text-white font-medium px-2.5 py-0.5 rounded-full text-xs\"\u003e\n                {totalSelectedCount.toLocaleString()}\n              \u003c/span\u003e\n              \u003cspan className=\"font-medium whitespace-nowrap text-sm\"\u003e\n                {totalSelectedCount === 1 ? 'Document' : 'Documents'} selected\n              \u003c/span\u003e\n            \u003c/div\u003e\n            \n            \u003cdiv className=\"h-6 w-px bg-gray-700\" /\u003e\n            \n            {/* Actions */}\n            \u003cdiv className=\"flex items-center gap-2\"\u003e\n              \u003cbutton\n                disabled={isPending}\n                onClick={() =\u003e handleAction('archive')}\n                className=\"flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-gray-800 transition-colors focus:ring-2 focus:ring-gray-400 focus:outline-none disabled:opacity-50\"\n              \u003e\n                \u003csvg className=\"w-4 h-4\" fill=\"none\" viewBox=\"0 0 24 24\" stroke=\"currentColor\"\u003e\n                  \u003cpath strokeLinecap=\"round\" strokeLinejoin=\"round\" strokeWidth={2} d=\"M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4\" /\u003e\n                \u003c/svg\u003e\n                Archive\n              \u003c/button\u003e\n              \n              \u003cbutton\n                disabled={isPending}\n                onClick={() =\u003e handleAction('delete')}\n                className=\"flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium text-red-400 hover:bg-gray-800 hover:text-red-300 transition-colors focus:ring-2 focus:ring-red-400 focus:outline-none disabled:opacity-50\"\n              \u003e\n                \u003csvg className=\"w-4 h-4\" fill=\"none\" viewBox=\"0 0 24 24\" stroke=\"currentColor\"\u003e\n                  \u003cpath strokeLinecap=\"round\" strokeLinejoin=\"round\" strokeWidth={2} d=\"M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16\" /\u003e\n                \u003c/svg\u003e\n                Delete\n              \u003c/button\u003e\n            \u003c/div\u003e\n\n            \u003cdiv className=\"h-6 w-px bg-gray-700\" /\u003e\n            \n            {/* Close / Dismiss */}\n            \u003cbutton\n              onClick={clearSelection}\n              className=\"p-1 hover:bg-gray-800 rounded-full transition-colors focus:ring-2 focus:ring-gray-400 focus:outline-none\"\n              aria-label=\"Clear selection\"\n            \u003e\n              \u003csvg className=\"w-5 h-5 text-gray-400\" fill=\"none\" viewBox=\"0 0 24 24\" stroke=\"currentColor\"\u003e\n                \u003cpath strokeLinecap=\"round\" strokeLinejoin=\"round\" strokeWidth={2} d=\"M6 18L18 6M6 6l12 12\" /\u003e\n              \u003c/svg\u003e\n            \u003c/button\u003e\n          \u003c/div\u003e\n        \u003c/div\u003e\n      )}\n    \u003c/div\u003e\n  );\n}\n```","toolAction":"Finishing the task","toolSummary":"Finish with the complete React component inline"}