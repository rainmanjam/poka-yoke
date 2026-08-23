Used the `poka-yoke:ux` skill since bulk delete/archive on documents is exactly the destructive-bulk-action case it targets — the real hazard here isn't "does the button work," it's that a selection can span thousands of documents the user never looked at.

**Key design decisions, made without asking:**
- Selection has two modes: an explicit `Set<string>` of ids for page-scoped picks, and a `filter + excludeIds` mode for "select all N matching" — you can't hold 4,000 ids in a checkbox state sanely, so the "all matching" case is described to the server, not enumerated on the client.
- Archive and Delete both assume soft-delete (Trash w/ retention) server-side, so both get the same low-friction path: optimistic-feeling, immediate undo toast, no modal — for selections fully visible on the current page.
- A confirmation dialog only appears when the selection spans beyond what's on screen (mode is "all-matching," or includes ids from another page). It states the exact count and consequence, never "are you sure."
- Idempotency key on every bulk request guards against double-submit from a flaky network or a fast double-click.

```tsx
// types.ts
export interface Document {
  id: string
  title: string
  updatedAt: string
  ownerName: string
}

export interface DocumentFilter {
  search?: string
  ownerId?: string
  status?: 'active' | 'archived'
}
```

```tsx
// api/bulkDocumentActions.ts
import type { DocumentFilter } from '../types'

export type BulkAction = 'archive' | 'delete'

interface BulkActionResponse {
  requestId: string
  affectedCount: number
  undoToken: string
  undoExpiresAt: string // ISO timestamp — server is the source of truth for the grace window
}

class BulkActionError extends Error {
  constructor(public status: number, public body: unknown) {
    super('Bulk document action failed')
  }
}

async function postBulkAction(body: Record<string, unknown>): Promise<BulkActionResponse> {
  const res = await fetch('/api/documents/bulk-actions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    throw new BulkActionError(res.status, await res.json().catch(() => null))
  }
  return res.json()
}

// Selection is an explicit list of ids — used when the user picked rows by hand.
export function bulkActionByIds(action: BulkAction, documentIds: string[], requestId: string) {
  return postBulkAction({ action, documentIds, requestId })
}

// Selection is "everything matching this filter, minus what they unchecked" —
// used for "select all N matching documents." The server resolves the ids, not the client.
export function bulkActionByFilter(
  action: BulkAction,
  filter: DocumentFilter,
  excludeDocumentIds: string[],
  requestId: string,
) {
  return postBulkAction({ action, filter, excludeDocumentIds, requestId })
}

export function undoBulkAction(undoToken: string): Promise<void> {
  return fetch('/api/documents/bulk-actions/undo', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ undoToken }),
  }).then(res => {
    if (!res.ok) throw new BulkActionError(res.status, null)
  })
}
```

`★ Insight ─────────────────────────────────────`
The two mutation entry points (`bulkActionByIds` vs `bulkActionByFilter`) exist because "select all 4,312 matching documents" can't be expressed as a client-side id list — you'd have to fetch and hold thousands of ids just to send them back. Sending the filter instead means the server (which already has the query) resolves scope once, atomically, rather than the client racing to enumerate a moving target.
`─────────────────────────────────────────────────`

```tsx
// useDocumentSelection.ts
import { useCallback, useMemo, useState } from 'react'

type SelectionState =
  | { mode: 'page'; ids: Set<string> }
  | { mode: 'all-matching'; excludedIds: Set<string> }

const EMPTY: SelectionState = { mode: 'page', ids: new Set() }

export function useDocumentSelection(totalMatching: number) {
  const [selection, setSelection] = useState<SelectionState>(EMPTY)

  const toggleRow = useCallback((id: string, checked: boolean) => {
    setSelection(prev => {
      if (prev.mode === 'page') {
        const next = new Set(prev.ids)
        checked ? next.add(id) : next.delete(id)
        return { mode: 'page', ids: next }
      }
      const next = new Set(prev.excludedIds)
      checked ? next.delete(id) : next.add(id)
      return { mode: 'all-matching', excludedIds: next }
    })
  }, [])

  const selectPage = useCallback((pageIds: string[]) => {
    setSelection({ mode: 'page', ids: new Set(pageIds) })
  }, [])

  const selectAllMatching = useCallback(() => {
    setSelection({ mode: 'all-matching', excludedIds: new Set() })
  }, [])

  const clear = useCallback(() => setSelection(EMPTY), [])

  const isSelected = useCallback(
    (id: string) =>
      selection.mode === 'page' ? selection.ids.has(id) : !selection.excludedIds.has(id),
    [selection],
  )

  const count = useMemo(
    () => (selection.mode === 'page' ? selection.ids.size : totalMatching - selection.excludedIds.size),
    [selection, totalMatching],
  )

  return { selection, count, toggleRow, selectPage, selectAllMatching, clear, isSelected }
}
```

```tsx
// BulkActionsBar.tsx
interface BulkActionsBarProps {
  count: number
  busy: boolean
  onArchive: () => void
  onDelete: () => void
  onClear: () => void
}

export function BulkActionsBar({ count, busy, onArchive, onDelete, onClear }: BulkActionsBarProps) {
  if (count === 0) return null

  return (
    <div
      role="region"
      aria-label="Bulk actions"
      className="sticky top-0 z-10 flex items-center justify-between gap-4 rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-sm"
    >
      <div className="flex items-center gap-3">
        <span className="text-sm font-medium text-slate-900">{count.toLocaleString()} selected</span>
        <button type="button" onClick={onClear} className="text-sm text-slate-500 hover:underline">
          Clear
        </button>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={onArchive}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Archive
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onDelete}
          className="rounded-md border border-red-200 bg-red-50 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Delete
        </button>
      </div>
    </div>
  )
}
```

```tsx
// ConfirmBulkActionDialog.tsx
import type { BulkAction } from './api/bulkDocumentActions'

interface ConfirmBulkActionDialogProps {
  action: BulkAction
  count: number
  onConfirm: () => void
  onCancel: () => void
}

// Only rendered when the selection spans beyond what's visible on the current page —
// a plain undo toast is enough for anything the user can already see.
export function ConfirmBulkActionDialog({ action, count, onConfirm, onCancel }: ConfirmBulkActionDialogProps) {
  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-slate-900/40 p-4">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="bulk-confirm-title"
        className="w-full max-w-sm rounded-lg bg-white p-5 shadow-lg"
      >
        <h2 id="bulk-confirm-title" className="text-base font-semibold text-slate-900">
          {action === 'delete' ? 'Delete' : 'Archive'} {count.toLocaleString()} documents?
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          This includes documents outside the current page.{' '}
          {action === 'delete'
            ? 'Deleted documents move to Trash and can be restored for 30 days.'
            : 'You can unarchive them at any time.'}
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="rounded-md px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-100">
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={
              action === 'delete'
                ? 'rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700'
                : 'rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800'
            }
          >
            {action === 'delete' ? 'Delete' : 'Archive'} {count.toLocaleString()}
          </button>
        </div>
      </div>
    </div>
  )
}
```

```tsx
// UndoToast.tsx
import { useEffect } from 'react'

interface UndoToastProps {
  message: string
  onUndo: () => void
  onExpire: () => void
  durationMs?: number
}

export function UndoToast({ message, onUndo, onExpire, durationMs = 8000 }: UndoToastProps) {
  useEffect(() => {
    const timer = setTimeout(onExpire, durationMs)
    return () => clearTimeout(timer)
  }, [onExpire, durationMs])

  return (
    <div
      role="status"
      className="fixed bottom-4 left-1/2 z-30 flex -translate-x-1/2 items-center gap-3 rounded-md bg-slate-900 px-4 py-2.5 text-sm text-white shadow-lg"
    >
      <span>{message}</span>
      <button type="button" onClick={onUndo} className="font-medium text-sky-300 hover:text-sky-200">
        Undo
      </button>
    </div>
  )
}
```

```tsx
// DocumentsTable.tsx
import { useState } from 'react'
import type { Document, DocumentFilter } from './types'
import { useDocumentSelection } from './useDocumentSelection'
import { BulkActionsBar } from './BulkActionsBar'
import { ConfirmBulkActionDialog } from './ConfirmBulkActionDialog'
import { UndoToast } from './UndoToast'
import { bulkActionByIds, bulkActionByFilter, undoBulkAction, type BulkAction } from './api/bulkDocumentActions'

interface DocumentsTableProps {
  documents: Document[] // current page, up to 50 rows
  totalMatching: number // total across all pages for the active filter
  filter: DocumentFilter
  pageSize: number
}

interface PendingUndo {
  action: BulkAction
  count: number
  undoToken: string
}

export function DocumentsTable({ documents, totalMatching, filter, pageSize }: DocumentsTableProps) {
  const selection = useDocumentSelection(totalMatching)
  const [confirming, setConfirming] = useState<BulkAction | null>(null)
  const [busy, setBusy] = useState(false)
  const [pendingUndo, setPendingUndo] = useState<PendingUndo | null>(null)
  const [error, setError] = useState<string | null>(null)

  const pageIds = documents.map(d => d.id)
  const visibleSelectedCount = pageIds.filter(id => selection.isSelected(id)).length
  // True once the selection includes something the user can't currently see —
  // that's the moment a plain undo toast stops being enough.
  const spansBeyondPage = selection.selection.mode === 'all-matching' || selection.count > visibleSelectedCount

  async function runBulkAction(action: BulkAction) {
    const requestId = crypto.randomUUID() // idempotency key: survives retries and double-clicks
    setBusy(true)
    setError(null)
    try {
      const response =
        selection.selection.mode === 'all-matching'
          ? await bulkActionByFilter(action, filter, [...selection.selection.excludedIds], requestId)
          : await bulkActionByIds(action, [...selection.selection.ids], requestId)

      setPendingUndo({ action, count: response.affectedCount, undoToken: response.undoToken })
      selection.clear()
    } catch {
      setError(`Couldn't ${action} ${selection.count.toLocaleString()} documents. Try again.`)
    } finally {
      setBusy(false)
    }
  }

  function requestBulkAction(action: BulkAction) {
    if (spansBeyondPage) {
      setConfirming(action)
    } else {
      runBulkAction(action)
    }
  }

  async function handleUndo() {
    if (!pendingUndo) return
    const { undoToken } = pendingUndo
    setPendingUndo(null)
    try {
      await undoBulkAction(undoToken)
    } catch {
      setError('Undo failed — the change already went through.')
    }
  }

  return (
    <div className="space-y-3">
      <BulkActionsBar
        count={selection.count}
        busy={busy}
        onArchive={() => requestBulkAction('archive')}
        onDelete={() => requestBulkAction('delete')}
        onClear={selection.clear}
      />

      {selection.selection.mode === 'page' &&
        pageIds.length > 0 &&
        selection.selection.ids.size === pageIds.length &&
        totalMatching > pageSize && (
          <p className="px-1 text-sm text-slate-600">
            All {pageSize} documents on this page are selected.{' '}
            <button type="button" onClick={selection.selectAllMatching} className="font-medium text-sky-700 hover:underline">
              Select all {totalMatching.toLocaleString()} matching documents
            </button>
          </p>
        )}

      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-slate-500">
            <th className="w-10 py-2">
              <input
                type="checkbox"
                aria-label="Select all on this page"
                checked={pageIds.length > 0 && pageIds.every(id => selection.isSelected(id))}
                ref={el => {
                  if (el) {
                    el.indeterminate = pageIds.some(id => selection.isSelected(id)) && !pageIds.every(id => selection.isSelected(id))
                  }
                }}
                onChange={e => (e.target.checked ? selection.selectPage(pageIds) : selection.clear())}
              />
            </th>
            <th className="py-2 font-medium">Title</th>
            <th className="py-2 font-medium">Owner</th>
            <th className="py-2 font-medium">Updated</th>
          </tr>
        </thead>
        <tbody>
          {documents.map(doc => (
            <tr key={doc.id} className="border-b border-slate-100">
              <td className="py-2">
                <input
                  type="checkbox"
                  aria-label={`Select ${doc.title}`}
                  checked={selection.isSelected(doc.id)}
                  onChange={e => selection.toggleRow(doc.id, e.target.checked)}
                />
              </td>
              <td className="py-2 text-slate-900">{doc.title}</td>
              <td className="py-2 text-slate-600">{doc.ownerName}</td>
              <td className="py-2 text-slate-600">{new Date(doc.updatedAt).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {error && (
        <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}

      {confirming && (
        <ConfirmBulkActionDialog
          action={confirming}
          count={selection.count}
          onCancel={() => setConfirming(null)}
          onConfirm={() => {
            setConfirming(null)
            runBulkAction(confirming)
          }}
        />
      )}

      {pendingUndo && (
        <UndoToast
          message={`${pendingUndo.count.toLocaleString()} document${pendingUndo.count === 1 ? '' : 's'} ${
            pendingUndo.action === 'delete' ? 'moved to Trash' : 'archived'
          }.`}
          onUndo={handleUndo}
          onExpire={() => setPendingUndo(null)}
        />
      )}
    </div>
  )
}
```

`★ Insight ─────────────────────────────────────`
The header checkbox uses `indeterminate` set via a ref callback rather than a prop — React (and the DOM) has no attribute for the mixed state, it's a property you have to set imperatively on the element itself.
`─────────────────────────────────────────────────`

**What this makes impossible, and what's left on purpose:**
- Rung 1: a hard-delete with no recovery path can't happen from this bar — both actions assume the backend soft-deletes, so the worst case is "in Trash for 30 days," not gone.
- Rung 2: a bulk action whose true scope is invisible (a filtered "all-matching" selection, or leftover picks from a prior page) is stopped by a dialog naming the exact count, not a generic "are you sure."
- Left on purpose: selecting and deleting everything visible on the current page (≤50, all on screen) skips the dialog entirely — the user can already see what they're affecting, so a confirm step there would only be trained-through friction, per the skill's restraint principle.

One real assumption baked in: the backend supports soft-delete/restore and a server-side `undoToken` with its own expiry. If Delete is actually permanent there, the Delete path needs a stronger device (typed confirmation), not this one — say the word and I'll swap it in.