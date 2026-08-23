Short answer: nothing is wrong with the wording. The instruction is the wrong *kind* of thing.

## Why caps and repetition don't help

A line in CLAUDE.md is **training** — rung 0 on the poka-yoke ladder. It relies on the agent remembering, and memory degrades in exactly the situations you're seeing ~10% of the time:

- **Context compaction** — after a long session the file's text is summarized or dropped.
- **Subagents** — dispatched agents often never see CLAUDE.md at all.
- **Pressure** — when a push is rejected or a generated file is "obviously" the quickest fix, "NEVER" competes with "finish the task" and sometimes loses.

Shouting louder at an operator was exactly what Shingo said doesn't work. A ~10% miss rate on a memorized rule isn't a wording failure; it's the expected decay rate of rung 0. Anything you write in prose will plateau around there.

## What to install instead (Control rung — the mistake can't happen)

**Force-push**

1. `.claude/settings.json` (committed, so it applies on every machine):
   ```jsonc
   { "permissions": { "deny": [
     "Bash(git push --force:*)",
     "Bash(git push -f:*)",
     "Bash(git push --force-with-lease:*)"   // drop this line if you want lease pushes allowed
   ] } }
   ```
2. **GitHub branch protection / rulesets** on `main` blocking force pushes. This is the real control — it holds even if the agent runs `git` through a different tool, a subagent, or a shell the hook doesn't see. The local deny is just a faster, friendlier error.

**`src/generated/`**

1. Deny rules: `"Edit(./src/generated/**)"`, `"Write(./src/generated/**)"`.
2. A header in every generated file: `// GENERATED — do not edit; run \`make codegen\`` — agents read the file before editing and this redirects them to the right action.
3. CI job that re-runs codegen and fails on diff — catches anything that slips through `sed` or other Bash paths the Edit deny doesn't cover.

The deny *message* matters: a bare block leads to a workaround attempt (`sed -i` on the file, `git push origin +main`). A `PreToolUse` hook like `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py` returns a reason naming the safe alternative, which is what actually changes behavior.

## What to do with the CLAUDE.md lines

Keep one short sentence each as a *fact* ("`src/generated/` is produced by `make codegen`"), delete the caps and the duplicates. Prose should explain where things live and why; enforcement belongs in the harness.

## Recap

The instructions aren't badly written — they're the wrong tool. ~10% failure is the natural decay of a remembered rule. Move both rules into `settings.json` deny entries plus a server-side control (branch protection; CI codegen check), keep CLAUDE.md for facts, and test each device by attempting the blocked action once.

The one decision that's yours: whether `--force-with-lease` should be allowed on non-main branches. Tell me that and I can write the `settings.json`, hook wiring, and file header into the repo.