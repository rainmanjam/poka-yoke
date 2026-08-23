No — confirmation modals are weak mistake-proofing. They train users to click "yes" without reading, especially when the action is named something tempting like "Delete workspace."

**Better approaches** (poka-yoke hierarchy):

1. **Soft delete + trash** — workspace goes to a trash folder, recoverable for 30 days. User can self-serve restore. No support ticket needed.

2. **Undo toast** — "Workspace deleted. **Undo**" (5-second window). Catches immediate "oops" moments.

3. **Rename instead of delete** — suggest archiving/renaming to "Old - [name]" first. Reversible, searchable, no data loss.

4. **Delay destructive action** — delete request schedules deletion for 24 hours later, user gets email with cancel link.

★ Insight ─────────────────────────────────────
- Confirmation modals are **detection controls** (catch the mistake). Soft-delete is an **elimination control** (no permanent deletion exists).
- Support tickets = evidence your control failed. Design for zero tickets, not "fewer angry tickets."
- Best UX: user never realizes they made a mistake because the system made it reversible.
─────────────────────────────────────────────────

**What I need to recommend specifics:**

1. Do deleted workspaces have schema/data you need to preserve for restore?
2. How many "panic delete" tickets/month are you seeing?
3. Is there a legitimate reason to permanently delete immediately (compliance, storage cost)?

Once I know those, I can sketch the soft-delete implementation.