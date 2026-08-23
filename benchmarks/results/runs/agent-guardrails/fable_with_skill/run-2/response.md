I have what I need. Here's the answer.

## You're not doing anything wrong with the instructions. Instructions are the wrong tool.

CLAUDE.md is training, and training degrades — under long contexts, after compaction, and in subagents that never read the file at all. One-in-ten is roughly what prose enforcement gets you, and caps and repetition don't move that number. The fix is a **device** that refuses the action before it executes, not better wording.

Both your rules can be devices today. Here's the full replacement — five parts, because stopping after the first leaves you with a rule that *looks* enforced and isn't.

### 1. Deny rules (for "never force push")

`.claude/settings.json`, **committed** to the repo:

```jsonc
{
  "permissions": {
    "deny": [
      // poka-yoke: force-push destroys remote-only commits [control]
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      // poka-yoke: src/generated is rebuilt from source; edits are overwritten silently [control]
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)"
    ]
  }
}
```

This is evaluated before the tool runs, no scripting needed.

### 2. A hook where a pattern isn't enough

Deny rules match the **start** of a command. `git push origin main --force` and `git push -fu origin` slip past the two entries above. So force-push needs a `PreToolUse` hook that inspects the whole string. The generated-files rule is fine as a pure path deny — except for `Bash(sed -i ... src/generated/...)`, which a hook also catches.

Copy `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py` into your repo's `.claude/hooks/` and wire it:

```jsonc
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash|Edit|Write",
      "hooks": [{ "type": "command",
                  "command": "python3 \"${CLAUDE_PROJECT_DIR}\"/.claude/hooks/guard_dangerous_commands.py" }]
    }]
  }
}
```

Its force-push regex already handles flag order and keeps `--force-with-lease` allowed. Add one rule to `RULES` for your generated dir:

```python
(r"\bsrc/generated/",
 "src/generated/ is rebuilt from the schema; hand edits are overwritten on the next build. "
 "Change the source (schema/ or the generator) and re-run `make generate` instead."),
```

### 3. The deny message is the device

The agent reads the reason and acts on it. A bare "denied" produces a workaround — often `--no-verify`, or editing the file via `cat >`. The message must say what was blocked, why, and what to do instead. That's the one place prose belongs.

### 4. Where it lives

`.claude/settings.json`, committed. A rule in `settings.local.json` protects one machine — the same failure as documenting it.

### 5. Prove it fires

An untested hook is worse than none; it creates confidence without protection.

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main --force"}}' | python3 .claude/hooks/guard_dangerous_commands.py
# expect: "deny" + reason mentioning --force-with-lease
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}' | python3 .claude/hooks/guard_dangerous_commands.py
# expect: no output
```

Then in a real session, ask Claude to edit a file in `src/generated/` and confirm the refusal and the message.

### Two smaller things

- **Add a header to every generated file** (`// GENERATED — do not edit; see schema/`). The agent reads the file before editing and that's the moment it matters.
- **Branch protection on the remote** for the force-push rule — it's a second layer that doesn't depend on any local config at all.

Once these are in, delete both lines from CLAUDE.md. What remains there should be facts (where the generator lives, how to re-run it), not commands you hope get followed.

I can write the settings.json and hook into your repo if you point me at it — I'll show you the config before it lands, since hooks run code on every tool call.