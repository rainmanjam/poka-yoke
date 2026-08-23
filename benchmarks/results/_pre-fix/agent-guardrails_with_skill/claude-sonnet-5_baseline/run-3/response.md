Confirmed: this repo has no `.claude/` settings directory yet, so nothing is actually wired up — your two rules exist only as prose in CLAUDE.md.

**Why "NEVER" in caps still fails ~1 in 10:** CLAUDE.md is a system prompt, not a policy engine. The model reads it, weighs it against everything else in context (your latest request, what it thinks is expedient, a plausible-sounding exception), and probabilistically complies. Repetition and capitalization raise the odds but never reach 100%, because there's no mechanism actually stopping the tool call — just a stronger suggestion not to make it. The two failure modes are almost always: an edit deep in a long session where the rule has scrolled out of recent attention, or a force-push framed as "obviously necessary" in the moment (e.g., "sync my branch," "clean up this mess").

**The fix: hooks, not stronger wording.** A `PreToolUse` hook runs deterministically before the tool executes and can literally return `deny` — the model never gets a vote. You already built this pattern: `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py` in this repo blocks `git push --force` (and reset --hard, rm -rf, DROP TABLE, etc.) exactly this way. It just isn't wired into this project's `.claude/settings.json`, and it has no rule yet for blocking edits under `src/generated/`.

Two options:
1. Wire up `guard_dangerous_commands.py` here (covers force-push already) and add a `PROTECTED_PATHS`-style regex for `src/generated/` to the `Edit`/`Write` check.
2. If you don't want the full poka-yoke guard script, I can write a minimal project-local hook that just denies those two things.

Want me to set this up now? It'll need a `.claude/settings.json` hook entry plus (for option 1) copying/adapting the existing script.