Using **poka-yoke:retro** — this is the "we agreed and it still keeps happening" shape.

## The finding

Separating the three things is the whole answer here:

- **Defect**: ~50% of PRs arrive unformatted/untyped.
- **Mistake**: someone commits without running the formatter.
- **Hazard**: **the repo accepts unformatted, untyped code.** Nothing between a developer's intent and `main` requires it.

Run the whys and don't stop at "they forgot": *why is forgetting possible?* → formatting is a recall step with no gate → *why is there no gate?* → the agreement was encoded as text, and **text is a request, not a constraint**.

So: CONTRIBUTING.md, the Slack pin, and two standups are all the same rung — rung zero. You've done that category three times. A fourth (a PR checklist item, a "formatting champion", an extra reviewer) will get you the same 50%. The honest answer to "what else can I do to get people to follow it" is *nothing* — stop trying to get people to follow it and make it not require following.

★ Insight ─────────────────────────────────────
50% compliance after clear communication usually isn't carelessness — it's that complying is *expensive*. Reformatting a legacy file makes a 400-line diff nobody wants to review; annotating new code that calls untyped legacy code cascades. Lowering the cost of the correct path is a device too, and it's the one most teams skip.
─────────────────────────────────────────────────

## Devices, by rung

| Device | Rung | Note |
|---|---|---|
| Formatter `--check` in CI, as a **required status check** in branch protection | Control | Unmergeable. Nobody has to ask, and no reviewer has to be the formatting police. |
| Type checker in CI **scoped to the diff** or frozen against a baseline file | Control | This is literally the "types on *new* code" agreement, mechanically expressed. |
| One-time repo-wide reformat + `.git-blame-ignore-revs` | Control (enabling) | Removes the exploding-diff excuse. Without this, the CI gate feels punitive. |
| Committed `.editorconfig` + `.vscode/settings.json` with format-on-save | Control | The formatter runs without anyone remembering it exists. |
| `pre-commit` hook | Warning | Fast feedback, but opt-in per clone and `--no-verify`-able. Complement to CI, never the gate. |
| CI bot that auto-formats and pushes | Control | Zero friction, but mutates contributor branches. |

## Then verify it

Per this repo's own rule — a check that has never gone red is a rumour. Open a throwaway PR with a deliberately mangled file and an untyped new function, watch CI refuse it, then fix and watch it pass. Track "% of PRs where the format job fails": it should hit ~0 within a week, and if it doesn't, the gate isn't actually required.

**The one decision that's yours:** fail-the-build vs. auto-format-and-push. Failing teaches the local setup and keeps history clean; auto-pushing removes friction entirely but rewrites people's branches under them. Which fits your team? Tell me your stack (Python/mypy? TS/tsc?) and I'll write the workflow and the baseline config.