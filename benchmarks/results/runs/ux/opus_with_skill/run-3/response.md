Using **poka-yoke:ux** (routed from the poka-yoke router skill) — destructive action in an interface.

Honest answer: it'll reduce the emails a bit, and it's the weakest device available to you. Here's why.

## What the modal actually does

The support emails tell you the real problem: **the delete is irreversible from the user's side.** A modal doesn't change that — it adds a speed bump in front of a cliff. And workspace delete is exactly the kind of action a modal is worst at: rare enough that nobody reads it, consequential enough that the one person who clicks through loses everything.

"Are you sure?" asks about the user's *resolve*. Resolve was never the problem — they meant to delete *something*, just not *that*. On the ladder in the skill, a generic confirm is rung 2 at best, and a dismissed-by-reflex one is rung 0.

## The ladder for this specific action

| Option | Rung | Note |
|---|---|---|
| Soft-delete + trash, 30-day retention | **1 — Control** | The mistake stops being a defect. No dialog needed at all. |
| Immediate delete + "Undo" toast, 10s | 1 | Good, but useless if they close the tab or notice tomorrow |
| Type the workspace name to confirm | 2 | Can't be done reflexively — pair with the above, don't substitute |
| "Are you sure?" modal | 2→0 | What you proposed |

**Recommendation: soft-delete with a retention window, and a type-the-name confirm on top.** The reason soft-delete is under-used is that it's a backend change and the modal is a two-hour frontend ticket — but you're already paying the backend cost today, manually, through support. Every panic email is a human running your undo procedure. Make it a device.

`★ Insight ─────────────────────────────────────`
- Support currently *is* your undo mechanism — which means the restore capability already exists, it's just gated behind a human. Exposing it is often cheaper than building it.
- A dialog that names the object and states scale ("Delete `acme-prod` — 47 projects, 12 members?") does fixed-value inspection. "This cannot be undone" does nothing.
- Retention makes the confirm text *honest*: "Recoverable for 30 days" is believable, so users stop learning to disbelieve your warnings.
`─────────────────────────────────────────────────`

## Where I need your call

Two decisions I shouldn't make for you, because they're policy, not code:

1. **Retention window and what happens at expiry.** 30 days is conventional. Trade-offs: storage cost, whether deleted workspaces still count against seat billing, and how it interacts with GDPR erasure requests (a hard-delete-on-request path has to bypass the trash).
2. **Who can restore** — any member, or owners only? Restore is a privilege escalation vector if a removed member can resurrect a workspace.

Tell me those two and point me at the delete handler, and I'll build it: soft-delete column + trash view + type-to-confirm, plus the server-side check that the restore endpoint enforces the permission rather than just hiding the button.