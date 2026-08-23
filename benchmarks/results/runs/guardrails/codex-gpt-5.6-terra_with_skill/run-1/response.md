Stop adding reminders; make the PR path reject violations.

- Run the formatter automatically in a pre-commit hook for fast feedback.
- Add a required CI check that runs the formatter in check-only mode. Protect the main branch so a failing check cannot merge.
- Require type checking in that same protected CI path. For existing untyped code, baseline current errors and ratchet: reject new type errors and require new modules to meet the stricter setting.
- Have CI comment or fail with the exact fix command, e.g. “Run `… format`” or “Add annotations / resolve these type errors.”
- Prove each gate: deliberately submit unformatted and untyped code, confirm CI blocks it, then fix it and confirm it passes.

The hook is a **warning** device—useful because it catches mistakes in seconds, but bypassable. Required CI plus branch protection is the actual **control**: unformatted or newly untyped changes cannot become merged defects. Your CONTRIBUTING entry, Slack pin, and standup reminders were all training; they cannot reliably enforce the rule.