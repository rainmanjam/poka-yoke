Short answer: **no** — an "are you sure?" modal is the weakest device on the ladder, and it won't fix the support emails. Here's the reasoning the skill lays out.

## Why the modal doesn't work

- Users delete things *on purpose* too. A dialog they see every time becomes click-through blindness — they'll press "Confirm" with the same reflex they press "OK". It protects nobody and taxes every legitimate delete.
- "Are you sure?" asks about **resolve**, not **facts**. The panicked user *was* sure. They were sure about the wrong workspace, or didn't realize what was inside it.
- The symptom you're describing — *emailing support in a panic* — is really "the delete is irreversible and I have no recourse." A modal doesn't change either of those.

## What to do instead, strongest first

| Device | Rung | What it fixes |
|---|---|---|
| **1. Soft-delete + trash with retention** (e.g. 30 days; "Restore" in the UI) | Control | The mistake has no permanent consequence. Support emails vanish because the user fixes it themselves. This is the real answer — it's a backend change, which is why it's under-used. |
| **2. Grace-period undo** — delete immediately, toast "Workspace *Acme Prod* deleted · **Undo**" for ~8s; or delayed commit (queue the delete, drop it if undone) | Control | Zero friction on the happy path, full recovery on the mistaken one. The easier build if true reversal is hard. |
| **3. Type-to-confirm** — only if a workspace is genuinely irreversible, high-blast-radius (GitHub repo deletion) | Warning | Can't be done reflexively. Don't use everywhere or it becomes theater. |
| **4. A dialog that names facts** — "Delete **Acme Prod**? 14 members, 2,310 documents. Recoverable for 30 days." Button reads "Delete workspace", not "OK"; Cancel gets default focus. | Warning | A count is fixed-value inspection. "Are you sure?" is not. |

My recommendation: **do #1 (or #2 if #1 is expensive), and pair it with #4's wording.** If you do only one thing, make it soft-delete — that's the device that actually deletes the support ticket category.

Also check while you're in there:
- **Adjacency** — is Delete next to Save/Leave on the same menu, same visual weight? Move it under a settings section, styled differently.
- **Permissions** — hiding the button isn't a device; make sure the endpoint refuses non-owners (that's the `authz` half).

★ Insight ─────────────────────────────────────
- Shingo's ladder: *control* (mistake impossible) > *warning* (announced) > *detection*. A modal is a warning at best; reversibility is control. Reach for the highest rung you can afford.
- "Undo beats confirm": friction is paid on every legitimate use; the mistake is rare. Put the cost on the rare path, not the common one.
─────────────────────────────────────────────────

**Recap:** Routed via the `poka-yoke` router to the `ux` skill. Verdict: skip the "are you sure?" modal; it's rung 0–2 and trains dismissal. Implement soft-delete with a trash/restore (rung 1), or at minimum immediate-delete-with-undo, and if a dialog remains, make it name the workspace, its contents, and its recoverability. If you share the delete handler and component, I can propose the concrete change in your stack.