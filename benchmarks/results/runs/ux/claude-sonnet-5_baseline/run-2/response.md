No — a modal alone won't fix this, and this exact scenario is *why* the guidance exists.

**The problem with "are you sure?":** it's rung-0 protection. Users who delete workspaces by accident are almost never being reckless — they're clicking through a routine flow on autopilot, and a generic confirm dialog is exactly the kind of thing autopilot clicks past. It stops nobody and adds friction to everyone. The dialog asks about resolve ("are you sure?"), not facts — it doesn't even tell them what they're about to lose.

**What actually closes this:**

1. **Make it reversible** (the real fix): soft-delete with a 30-day trash/restore window. The mistake stops being catastrophic, so the panic emails to support stop too — there's a "how do I get it back" self-serve path instead.
2. **Grace-period undo**: delete immediately, show "Workspace deleted — Undo" for ~10s. Zero friction on intentional deletes, full recovery on the reflexive click.
3. If you want a gate on top of that, make it **proportional**: require typing the workspace name to confirm (GitHub repo-delete pattern) — not a generic "Are you sure?" Typing the name can't be clicked through reflexively.

A plain confirm modal is worth adding only as decoration on top of #1/#2, never as the sole device — it's the "warning in a modal everyone dismisses" example the skill calls out directly as rung 0.

Practical order of effort: soft-delete + restore (backend change, biggest win) → undo toast on the delete action → type-to-confirm if you still want a pre-delete gate.

Want me to spec out the soft-delete schema and the restore flow, or scope this to frontend-only (undo toast on top of your existing hard-delete)?