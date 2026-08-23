Not quite — and we actually worked through this earlier today (05:18–06:00 in this session): a confirm modal was the wrong device here.

The problem with "are you sure?" is that it's rung-0 protection — it relies on the user reading it, and once someone deletes/confirms workspaces even occasionally, the dialog becomes muscle memory. It stops nobody and adds friction to every legitimate delete.

What actually fixes "users panic-email support after deleting a workspace" is making the action **reversible**, not harder to trigger:
- **Soft-delete** the workspace instead of destroying it immediately
- **30-day trash/grace period** before permanent purge
- **"Deleted. Undo" toast** right after the action — Gmail's undo-send pattern

That gives you zero friction on the 99.9% of deletes that are intentional, and full recovery on the ones that aren't — which is strictly better than a modal for the actual support-ticket problem you're trying to kill.

From earlier, three things were blocking implementation and never got decided:
1. What happens to billing/seats for a workspace sitting in the grace period?
2. Can a deleted workspace's slug/URL be reused before the 30 days is up?
3. Who has permission to restore — any admin, or only the person who deleted it?

Want to make those three calls now so I can implement soft-delete + trash + undo, or do you want the modal anyway for some reason specific to your case (e.g. compliance requires an explicit acknowledgment step)?