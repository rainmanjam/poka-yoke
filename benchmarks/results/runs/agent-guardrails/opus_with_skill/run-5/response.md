Read the router (`plugins/poka-yoke/skills/poka-yoke/SKILL.md`) and it routes here to **`agent-guardrails`** — "CLAUDE.md says X but it still does Y" is that skill's opening line.

## Nothing is wrong with the instructions

Both rules are rung zero. A line in CLAUDE.md is *training*, and training degrades — under long contexts, after compaction, and in subagents that never read the file at all. Caps and repetition don't change the mechanism; ~1-in-10 is just what a probabilistic instruction looks like. Both of your rules are irreversible actions, which is exactly where you need Control (mistake impossible), not Warning.

Here's the replacement.

**1. Deny rules — `.claude/settings.json`, committed** (not `settings.local.json`; that protects one machine, which is the same failure as documenting it):

```jsonc
{
  "permissions": {
    "deny": [
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)",
      "Bash(git push --force:*)",
      "Bash(git push -f:*)"
    ]
  }
}
```

**2. A hook, because for force-push the pattern is not enough.** Deny entries match the *start* of the command, so `cd api && git push -f`, `git push origin main --force`, and `git push --force-with-lease` (which is the safe form and should stay allowed) all fall outside those two lines. Same for `src/generated/` via `sed -i` or a heredoc in Bash. Copy `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py` into `.claude/hooks/` — its first rule already handles force-push correctly, including the `--force-with-lease` carve-out — and wire it:

```jsonc
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash|Edit|Write|Read",
        "hooks": [{ "type": "command",
          "command": "python3 \"${CLAUDE_PROJECT_DIR}\"/.claude/hooks/guard_dangerous_commands.py" }] }
    ]
  }
}
```

**3. The deny message is the device.** A bare refusal produces a creative workaround. For generated files it needs to name the source: *"Blocked: `src/generated/` is codegen output — edits here are overwritten on the next build. Change the schema/template it's generated from and re-run `<your codegen command>`."* Without that sentence the agent will reach for `sed`.

**4. Proof it fires** — an untested hook fails open while looking like protection:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"cd api && git push -f origin main"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect: deny + reason
echo '{"tool_name":"Bash","tool_input":{"command":"git push --force-with-lease"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect: no output
```

**5. What the hooks still don't cover:** they only bind *this* agent. Force-push by a human, a CI job, or another tool needs branch protection on the remote — that's the actual Control rung. And `src/generated/` needs a CI check that regenerating produces no diff, otherwise a stale committed artifact is still possible.

`★ Insight ─────────────────────────────────────`
The force-push rule and the generated-files rule fail differently: force-push is *irreversible*, so it needs Control; a bad edit to `src/generated/` is recoverable via git, so its real cost is silent drift — which is why it wants a CI equality check as much as a deny.
`─────────────────────────────────────────────────`

One decision shapes the config, and it's yours: does your codegen write through `Write`/`Edit` (in which case a blanket deny breaks your own build and the hook needs an allowance for the codegen command) or does it run as a Bash script that the `Edit` deny never sees? Tell me which, and whether you want me to write `.claude/settings.json` and copy the hook into the target repo — I haven't touched any files yet, since hooks execute code on your machine on every tool call.