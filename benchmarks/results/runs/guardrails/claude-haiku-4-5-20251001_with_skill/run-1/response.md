★ Insight ─────────────────────────────────────
The fundamental problem: you've put the rule in rung 0 (training/documentation), and rung 0 doesn't work. Half your team follows it by habit or habit-by-agreement; the other half simply doesn't remember when they're heads-down. This isn't a character flaw, it's how attention works.

The device you need is rung 1 (control — the mistake becomes impossible) or rung 2 (warning — instant announcement at the moment it happens). A pre-commit hook gives warning but is bypassable (`--no-verify`). Only CI + branch protection gives control.
─────────────────────────────────────────────────

## The mistakes to stop

1. **Unformatted code merged** — someone skips the formatter or never runs it
2. **Missing type annotations on new code** — types don't exist or are `any`/implicit

## The proposed device architecture

**On the dev machine (pre-commit hook):**
- Format check + auto-fix on changed files (seconds, low friction)
- Type check on changed files (TypeScript: `tsc --noEmit` or similar)
- Feedback while context is fresh

**In CI (required, backed by branch protection):**
- Same checks (format + type), run on the PR branch
- Block merge if either fails
- This is the real enforcement — pre-commit is just ergonomic

**Key tradeoff — "baseline first, then ratchet":**
If you have a large codebase with a lot of unformatted code already, enabling strict formatting on every file will fail on every PR immediately and the rule gets reverted by Friday. Instead, in the first week:
- Enforce on **changed files only** (not the entire codebase)
- Or run the formatter in CI to auto-fix and commit the result (a `pre-push` or CI script that fixes format and force-pushes the branch)

Then, over 2–4 weeks, gradually ratchet the baseline up (requiring *new* violations to be fixed before merge, but not old ones).

## What needs to be wired

Before I write config files, I need to know:

1. **What's your stack?** (TypeScript + Node? Python? JavaScript? Mixed?)
2. **Which formatter?** (Prettier, Ruff, Black, etc.)
3. **Type checker?** (tsc for TypeScript, mypy for Python, etc.)
4. **What's on pre-existing code?** Is most of it formatted/typed, or is there a legacy backlog?

Once you clarify, I'll build:
- `.pre-commit-config.yaml` (for the hook)
- A CI workflow step or required check (GitHub Actions? Other?)
- The exact branch protection settings to click
- A test: write a deliberately unformatted/untyped piece of code, show it failing the hook and CI, then fix it and show it passing

That's the shape that actually sticks. Does that direction make sense?