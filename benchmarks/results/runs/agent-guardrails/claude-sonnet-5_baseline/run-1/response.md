Short answer: nothing wrong with the wording — the problem is that CLAUDE.md is a memory aid, not an enforcement layer, and you're using it as the latter.

**Why caps + repetition doesn't close the gap**

CLAUDE.md text competes for attention like everything else in context. It degrades under exactly the conditions you're least likely to notice: long sessions, context compaction/summarization, and subagents spawned mid-task that never load the parent's CLAUDE.md at all. "NEVER," said twice, is still a probabilistic prior on what the model does next — not a gate the harness checks before acting. A ~1-in-10 violation rate is roughly what you'd expect from instruction-following alone; it's not going to converge to 0 by adding a third exclamation point. (I checked — this repo has no `.claude/settings.json` at all, so right now these two rules exist *only* as prose. There's no device backing them.)

The fix is to move both rules out of text and into something the harness enforces before the tool call runs.

**1. `src/generated/` — a plain deny rule is enough**, since it's just a path match:

```jsonc
// .claude/settings.json
{
  "permissions": {
    "deny": [
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)"
    ]
  }
}
```

**2. Force-push needs a hook, not a deny pattern.** A string-prefix deny like `"Bash(git push --force:*)"` only catches `--force` as the *first* thing after `git push`. It won't catch `git push origin main --force`, `git push -f`, or `--force-with-lease` in arbitrary position. Those variations are exactly why this one still slips through — a permission pattern can't see flag position, a hook can:

```jsonc
// .claude/settings.json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "command",
        "command": "/bin/bash -c 'read -r input; cmd=$(echo \"$input\" | jq -r .tool_input.command); if echo \"$cmd\" | grep -qE \"git push.*(--force([^-]|$)|-f\\b|--force-with-lease)\"; then echo \"{\\\"decision\\\":\\\"block\\\",\\\"reason\\\":\\\"Blocked: force-push detected in `\"$cmd\"`. This can overwrite remote history other people depend on. If you genuinely need to force-push, ask the user to run it themselves.\\\"}\"; fi'"
      }]
    }]
  }
}
```
(Point `update-config` at this if you want it written properly with a real script file instead of inline bash — inline one-liners like this get unreadable fast.)

**3. The deny/block message matters as much as the rule.** A bare "denied" gets the agent creatively working around it (e.g., `git push --delete` + re-push, or committing straight to `src/generated/` under a different tool). The message above names what was blocked and what to do instead — that's the one place prose still belongs.

**4. Put this in `.claude/settings.json` and commit it**, not `settings.local.json`. Local-only protection is the same failure mode as documenting it in CLAUDE.md — it only works on the machine of whoever set it up.

**5. Prove it before trusting it.** Try an actual force-push and an actual edit to a file under `src/generated/` and confirm both the denial and the message fire; then confirm an ordinary push and an ordinary edit elsewhere still work. An untested hook is worse than none — a regex that doesn't match the real command string looks like protection while doing nothing.

Want me to actually write the `.claude/settings.json` (and a proper hook script file instead of the inline one-liner) into this repo? I'd show you the exact diff before applying it, since hooks run shell code on every matching tool call.