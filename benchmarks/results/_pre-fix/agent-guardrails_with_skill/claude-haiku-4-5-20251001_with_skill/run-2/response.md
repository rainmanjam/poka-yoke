Your CLAUDE.md rules are being **dropped by context compaction and subagents**, not ignored by Claude. This is a known ~10% failure rate for "training controls" (soft advisory rules) — they degrade as conversation history gets compressed and subagents spawn with partial context.

The session memory confirms this was already diagnosed:

> CLAUDE.md rule failures (~10%) as rung-0 training controls that degrade with context compaction/subagents; recommended settings.json deny rules + GitHub branch protection for force-push and deny rules + file headers + CI regeneration for src/generated/

**The fix requires hard enforcement, not just instructions:**

1. **GitHub branch protection** (server-side, unbypassable)
   - Deny force-push to main/master
   - Require status checks before merge

2. **settings.json deny rules** (harness-level, caught before execution)
   - Deny `git push --force*` commands
   - Deny Edit on `src/generated/**` files
   - These are checked by the harness before you even attempt the action

3. **Pre-commit hooks** (local, subprocess-level)
   - Prevent force-push at git hook time
   - Regenerate `src/generated/` on commits (so edits get stomped)

The skill `/update-config` can help set up settings.json deny rules. Would you like me to:
- Add deny rules for force-push and src/generated/ edits to your project settings.json?
- Walk through GitHub branch protection setup?
- Set up a pre-commit hook to regenerate src/generated/?

Which control layer matters most to you right now?