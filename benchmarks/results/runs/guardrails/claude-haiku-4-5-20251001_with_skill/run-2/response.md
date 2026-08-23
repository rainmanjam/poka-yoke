Your problem isn't communication—it's rung zero. You're documenting a rule instead of enforcing it. The poka-yoke answer: **move formatting and type checking from "please do this" to "this will not merge."**

The guardrails skill maps this precisely. You need:

1. **Type annotations**: A required CI check (`tsc --noEmit` or equivalent for your language). Make it fail the build. This is **Control** (rung 1)—unbypassable.

2. **Formatting**: Pre-commit hook for fast feedback + a required CI check with branch protection. Pre-commit hooks can be bypassed with `--no-verify`, so the CI gate is what actually enforces it. Same check runs in both places so they can't drift.

**Critical detail**: Don't enable these on all 500 existing lines if half your PRs are already failing. Baseline first, then ratchet:
- Lint/format the codebase *now* (one-time cleanup commit)
- Gate only *new* changes initially, or only changed files
- The violation count can only go down; a gate that fires constantly gets deleted

**Before you build**: Look at what assets are in `/plugins/poka-yoke/assets/devices/` for your stack—pre-commit templates, GitHub Actions workflows, etc. Read those first; they're ready to adapt.

The closing note from the skill: the whole point is that documentation stops working the moment someone is under deadline. A CI gate applies itself. Everyone remembers it because they can't forget it.

What's your primary language and CI/VCS setup? I can walk you through the specific config.