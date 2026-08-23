Using the poka-yoke `guardrails` skill for this.

Here's the diagnosis: CONTRIBUTING.md, Slack pins, and standup mentions are all rung 0 — they rely on someone remembering, and memory has a half-life of about one onboarding cycle. That's why formatting/typing compliance decayed to ~50% within two weeks even though everyone agreed to it. No amount of restating the rule fixes this, because the rule was never wired into anything that can refuse bad work.

The fix is to move the rule from documentation to a gate it can't bypass:

1. **Pre-commit hook** (fast, local) — runs the formatter and fails the commit if it's not clean. Catches it in seconds, but it's bypassable with `--no-verify`, so it's a courtesy, not enforcement.
2. **CI required check** (the real enforcement) — same formatter + type checker run in CI, wired into branch protection so the PR literally cannot merge if it fails. This is non-bypassable and is what actually holds the line.
3. **Baseline, don't boil the ocean** — if you turn strict type-checking on for the whole repo today, you'll get hundreds of pre-existing failures, the check will feel impossible to satisfy, and someone will disable it by Friday. Instead: enforce formatting/typing only on changed files (or generate a baseline of current violations and fail only on *new* ones). The violation count can only go down from there.
4. **Failure messages that teach** — a bare "lint failed" trains people to `--no-verify` past it. The message should say what's wrong and give the exact fix command (`ruff format .` / `npx prettier --write .`, etc.).

The pre-commit hook alone won't fix your problem — it's exactly the piece that gets skipped under deadline pressure. The CI required check + branch protection is what turns "half the PRs" into "PRs that don't pass don't exist."

To generate the actual config (pre-commit YAML, CI workflow, baseline setup), I need to know your stack — what language/formatter/type-checker (e.g., Python + ruff + mypy, or TypeScript + prettier + tsc)? And do you already have any CI workflow file I should extend rather than replace?