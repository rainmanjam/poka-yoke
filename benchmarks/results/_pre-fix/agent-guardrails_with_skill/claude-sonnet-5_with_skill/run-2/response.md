That confirms the diagnosis: there's no `.claude/settings.json` in this repo at all, so those CLAUDE.md rules have nothing enforcing them mechanically.

**What you're doing wrong:** you put the rules in CLAUDE.md, in caps, twice. That's rung zero — training, not a device. Per the poka-yoke framing, instructions to an agent degrade under long contexts, compaction, and subagents that never read the file. Capitalizing or repeating text doesn't change which rung it's on; a 1-in-10 failure rate is exactly what you'd expect from a prose rule under pressure, not a sign you phrased it wrong.

**The fix — move both rules to a deny rule, since neither needs conditional logic:**

Create `.claude/settings.json` (commit it — team-wide, not personal):

```jsonc
{
  "permissions": {
    "deny": [
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      "Edit(src/generated/**)",
      "Write(src/generated/**)"
    ]
  }
}
```

This alone gets both rules to Control: the tool call is refused before it executes, not caught after.

Two things worth doing beyond that deny block:

1. **Force-push**: a local deny only protects agents running with your config. If this matters enough to write in caps twice, also turn on server-side branch protection (GitHub: require PRs, block force-pushes on the branch) so it holds regardless of what's running locally. Note `--force-with-lease` is the safe form of force-push (won't clobber commits it hasn't seen) — decide if you want to allow that one through or block all force variants.
2. **`src/generated/`**: pair the deny with a header comment in the generated files themselves ("AUTO-GENERATED — do not edit, run `X` instead"). Belt-and-suspenders: the deny stops the agent, the header stops a human who edits directly and bypasses hooks.

The plugin in this repo already ships a `PreToolUse` hook (`plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py`) that catches force-push via regex on the Bash command — but it's not wired into any `.claude/settings.json`, so right now it isn't running either. The plain deny rules above are simpler and sufficient for these two cases; you don't need the hook unless you want conditional logic (e.g., allowing `--force-with-lease` but not `--force`, which the hook already does).

Want me to write `.claude/settings.json` with these rules?