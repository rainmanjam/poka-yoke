Hold on — you actually evaluated this already. Your memory shows you rejected the confirm-modal approach via poka-yoke testing because **users ignore frequent modals**. The recommendation was soft-delete + 30-day trash + undo toast instead, which fixes the problem without relying on people paying attention to a dialog.

A modal is training (it requires users to remember to read carefully each time), and by this repo's own philosophy, that's not a finished solution.

Did something change? Is the soft-delete approach blocked on those three design decisions you noted (billing/seats during grace, slug reuse, restore perms)? If so, let's unblock those instead of stepping back to the modal—it'll keep working even when users are tired or distracted.