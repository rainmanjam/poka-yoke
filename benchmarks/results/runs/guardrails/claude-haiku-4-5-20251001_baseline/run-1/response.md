You've done Rung 0 (training), and Shingo's finding was that training degrades. You're at 50% compliance because half the team either didn't see it, forgot, or consciously cut corners. Writing it down again won't help.

What you need are **devices** — Rung 1 (Control, impossible to merge unformatted code) or Rung 2 (Warning, catches it instantly and blocks the merge). Here's what that looks like:

**For formatting:**
- **Pre-commit hook** (warning) — runs the formatter on `git commit`, catches it immediately, fails if code isn't formatted
- **CI required check** (control) — runs the formatter as a test, merge is blocked if it fails
- Run the same check in both so `--no-verify` is painful but not a complete escape hatch

**For type annotations:**
- **Strict type checking in CI** (control) — `tsc --strict` or equivalent, blocks PRs that have unannotated code
- **ESLint/mypy rule** (warning/control) — catches bare `: any` or missing return types in the editor, optional in pre-commit

**The critical piece:** without branch protection that makes these checks *required to merge*, they're optional. Anyone in a hurry does `git commit --no-verify` and they're gone. So:

1. Add the hooks/checks (quick win)
2. Set branch protection to require the CI check to pass (the real enforcement)
3. Test them by intentionally writing unformatted code and watching them fail

The reason this works where "remember to do X" doesn't: the machine doesn't get tired, doesn't forget, and can't be negotiated with. Someone can *choose* to skip the hook, but they can't choose to merge — the branch protection is the teeth.

Want me to draft the config for your stack? I'd need to know: language (TS/Python/other?), existing CI setup, and whether you have a pre-commit config already.