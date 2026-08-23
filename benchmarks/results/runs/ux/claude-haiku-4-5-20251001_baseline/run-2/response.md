Not quite—that was already evaluated earlier today and rejected. Users ignore frequent modals, so a confirm dialog will likely just train people to click through without reading.

The better pattern that came up: **soft-delete with a 30-day trash + undo toast**. It gives users recovery without the friction of a scary modal they've learned to dismiss.

Three design decisions are still open though:
1. What happens to billing/seat allocations during the grace period?
2. Can they reuse the workspace slug after deletion?
3. Who can restore a deleted workspace?

Has something changed that makes the modal approach make sense now, or do you want to circle back to the soft-delete approach?