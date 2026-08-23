Honestly, no — not as the fix. An "Are you sure?" modal is the weakest device on the ladder for this problem, and it'll likely fail you in the exact way you're trying to avoid.

**Why it won't work**

The users emailing support in a panic aren't people who lacked resolve — they clicked delete *on purpose*, on the wrong thing, or without understanding the blast radius. "Are you sure?" asks about resolve; it doesn't tell them anything they didn't already believe. And once people see the modal a few times, they click through it reflexively. You'll add friction to every legitimate delete and still get the panic emails.

**What actually fixes it, strongest first**

1. **Make it reversible — soft-delete with a retention window.** Mark the workspace deleted, hide it, hard-purge after 7–30 days. Support's reply becomes "click Restore" instead of "sorry, it's gone." This is a backend change, not a UI change, which is why it gets skipped — but it's the only option that turns the incident into a non-event.
2. **Grace-period undo.** Delete immediately, show "Workspace deleted. Undo" for ~10s. Zero friction on the happy path, full recovery on the mistaken one. Needs #1 underneath it anyway.
3. **Type-to-confirm** (GitHub-style: type the workspace name). Only if deletion is *genuinely* irreversible and high-blast-radius. Can't be done reflexively, but it's theater if used for everything.
4. **A modal that states facts, not resolve.** If you do keep a modal, make it "Delete *Acme Prod* — 14 members, 2,300 documents, permanently?" That's a real check. "Are you sure?" is not.

**My recommendation:** do #1 and #2 together, and drop the modal entirely. If the data model makes soft-delete hard right now, do #4 as a stopgap — name the workspace, show the counts, make Delete the non-default button and visually separate it from Cancel — and put soft-delete on the roadmap as the real fix.

If you want, point me at the delete handler and the workspace model and I'll implement soft-delete + undo in your stack.