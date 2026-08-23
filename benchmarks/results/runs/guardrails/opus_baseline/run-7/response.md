## The short answer: nothing you say will move that number

You've now tried three devices — CONTRIBUTING.md, a pinned message, and standup — and they're all the same device: **training**. Training degrades. Half compliance after two weeks isn't a discipline problem on your team, it's the normal yield of a rule that depends on remembering. A fourth reminder gets you the same number.

The fix is to stop asking people to do it and make the machine do it (or refuse the work).

`★ Insight ─────────────────────────────────────`
Shingo's regulatory ladder: **Control** (mistake impossible) > **Warning** (announced the moment it happens) > **Detection** (found later) > **rung 0** (docs, reminders, checklists). Your three attempts are all rung 0. Every device below is rung 1 or 2.
`─────────────────────────────────────────────────`

**Formatting — this should stop being a rule at all.** Nobody should "remember to run the formatter." Three layers, cheapest first:

1. Commit the editor config to the repo (`.vscode/settings.json` with `formatOnSave`, or the `.editorconfig`) so it happens without anyone deciding to.
2. A pre-commit hook that formats **changed files only** — keep it under ~5 seconds or people will `--no-verify` it.
3. The same command as a **required CI check**. This is the one that actually holds; the hook is for speed, CI is for authority. Run the identical script in both so they can't drift.

**Types — this is where teams usually get it wrong.** Turning on `mypy --strict` / `tsc --noEmit` repo-wide produces hundreds of failures on legacy code, everyone learns to ignore the gate, and it's reverted by Friday. That's worse than not adding it. You need a **ratchet**: the violation count can only go down. Either check changed files only, or generate a baseline of existing violations and fail only on new ones.

**The piece that makes all of it real:** branch protection with these as required checks. Without it you've built a suggestion with extra steps. That's a settings change you have to make yourself — I can give you the exact `gh api` call.

**One thing to delete:** the CONTRIBUTING.md paragraph. Replace it with the command that fixes a failure. Prose belongs in exactly one place — the failure message, at the moment someone is guaranteed to read it. `error: 3 files unformatted — run 'make fmt'` teaches; `rule violated` produces a workaround.

---

**The decision that's actually yours**, because it depends on your codebase's history: changed-files-only, or a frozen baseline? Changed-files is simpler but lets an untouched bad file stay bad forever; a baseline gives you a real number that trends to zero but needs regenerating on big refactors.

Tell me which, plus your stack (Python → ruff + mypy; TS → prettier/biome + tsc), and I'll write the pre-commit config, the CI workflow, and the branch-protection command — then deliberately break each one so you can see it go red before you ship it to the team.