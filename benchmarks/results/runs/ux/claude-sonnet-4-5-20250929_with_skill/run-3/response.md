Not yet — that modal is **rung 0** (relies on reading) and won't solve the problem. Here's why:

## The hazard with "Are you sure?"

A generic confirmation users see repeatedly trains **click-through blindness** — they press "Confirm" reflexively, the same as "OK". The dialog adds friction to every legitimate deletion while preventing almost nothing. From the poka-yoke UX ladder:

> *A confirmation dialog a user sees fifty times a day stops being a decision point.*

## Better devices, strongest first

### 1. **Soft-delete + Trash (Rung 1: Control)** ← Start here
Make deletion **reversible** rather than gated:
- Move workspace to trash with 30-day retention
- Users can self-serve restore from trash
- Zero friction on the happy path, full recovery on mistakes
- **No confirmation dialog needed at all**

This is the real fix — it's a backend change, not just UI, which is why it gets skipped. But it's the only device that truly protects users.

### 2. **Grace-period undo (Rung 1: Control)** ← If soft-delete is blocked
- Delete immediately, show "Deleted workspace-name. **Undo**" toast for 10 seconds
- Gmail undo-send pattern
- Still zero friction, still recoverable

### 3. **Type-to-confirm (Rung 1: Control)** ← Only if truly irreversible
- Require typing the workspace name: `"Type 'production-api' to confirm"`
- Cannot be done reflexively — forces reading
- Use **only** for genuinely catastrophic actions; overused becomes theater

### 4. **Specific-consequence dialog (Rung 2: Warning)** ← If you must
If the action is irreversible and you can't do 1-3, the dialog needs **all four**:
1. Name the object: `"Delete 'production-api'?"` not `"Delete this workspace?"`
2. State the scale: `"3 projects and 1,204 files"`
3. State reversibility honestly: `"Cannot be recovered"` or `"Recoverable for 30 days"`
4. Button labeled with verb: `"Delete forever"` not `"OK"`

## What I need to know

**What prevents soft-delete?** Schema constraints? Storage costs? API contracts? Knowing the blocker determines which rung you can reach.

Once you decide, I'll help design and implement the device — but soft-delete with trash is the target, and everything else is a compromise we should name explicitly.