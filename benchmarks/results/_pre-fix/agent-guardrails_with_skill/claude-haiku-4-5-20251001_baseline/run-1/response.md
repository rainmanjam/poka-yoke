Looking at the memory from earlier in the session—you already diagnosed this! The issue isn't your instructions; it's that **text instructions in CLAUDE.md are "rung-0 training controls" that degrade under context compaction and subagent spawning**.

Here's what happens:

1. **Context compaction**: When the session grows long, older context (including CLAUDE.md) gets summarized away. The model loses the explicit instruction.
2. **Subagents**: When spawning an Agent, the subagent starts fresh—they don't retain the full context of your CLAUDE.md rules, even though there's auto-injection happening.
3. **Pressure**: Under latency/token constraints, the model may optimize for speed over rule adherence.

**Shouting the rule (caps, twice) doesn't solve this** because it's still text—still compressible, still losable in a subagent context.

The fix is **technical controls** (rung-2/3), which actually *prevent* the action:

**For `src/generated/`:**
- Add a deny rule in settings.json: `{"edit_paths": ["!src/generated/**"]}`
- Add file headers so CI regeneration tools understand what's generated
- Stop hand-editing; regenerate via CI instead

**For force-push:**
- GitHub branch protection on `main`: Require signed commits, or enforce CI passes
- Deny rule in settings.json: block any git command with `--force` flag
- Optional: allow only `--force-with-lease` (safer), or block all force entirely

Text instructions ask Claude nicely. Technical controls *make it impossible*.

Do you want me to draft those settings.json deny rules and a GitHub branch protection config?