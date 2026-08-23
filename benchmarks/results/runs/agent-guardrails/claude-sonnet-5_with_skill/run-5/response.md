CLAUDE.md rules are rung zero: they're training text, and training degrades under long contexts, compaction, and subagents that never load the file. "About one time in ten" isn't a fluke — that's the normal failure rate for prose the model has to remember to apply rather than something that's mechanically enforced. Fixing your wording won't move that number; installing a device will.

Here's the full replacement for both rules — a diagnosis alone would leave you exactly where you started.

**1. Deny rules — `.claude/settings.json` (commit this, not `.local.json`, or the protection only exists on your machine):**

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

The `src/generated/**` rule alone is enough — Control rung, no conditional logic needed, since it's a pure path match.

**2. A hook, because "never force push" needs one and a deny rule doesn't fully cover it.** Deny rules match the *start* of the command string. `git push --force origin main` matches `"Bash(git push --force:*)"`, but `git push origin main --force` or `git push origin main -f` do not — and that's a completely normal way for an agent to write the command. This is exactly the case the skill calls out: anything where the dangerous form isn't reliably the prefix needs a `PreToolUse` hook that inspects the whole string. There's already a ready-made one at `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py` with this regex for force-push, anchored so `--force-with-lease` stays allowed:

```python
(r"\bgit\s+push\b.*(--force(?!-with-lease)|(?<![\w-])-f(?![\w-]))",
 "Force-push can destroy commits that exist only on the remote. "
 "Use --force-with-lease if you must rewrite, and ask the user before rewriting shared history.")
```

Copy it into your repo at `.claude/hooks/guard_dangerous_commands.py` (hooks resolve against the project, not the plugin cache) and wire it up:

```jsonc
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "python3 \"${CLAUDE_PROJECT_DIR}\"/.claude/hooks/guard_dangerous_commands.py" }]
      }
    ]
  }
}
```

**3. The deny message is what actually redirects the agent** — a bare "denied" produces a workaround, often a worse one. The hook's message already names what was blocked, why, and the safe alternative (`--force-with-lease`). For the generated-files deny, add a matching header at the top of the generated files themselves (source inspection, catches the agent before it even tries):

```
// AUTO-GENERATED — do not edit. Edit the source and regenerate: <command>.
```

**4. Verify both fire, and that they don't over-block:**

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main --force"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect: deny, mentions --force-with-lease

echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect: no output
```

For the generated-files deny, actually try editing a file under `src/generated/` in a session and confirm you get a denial, then edit a neighboring non-generated file and confirm it still works.

Once both are in place and verified, the CLAUDE.md lines can stay — but as a fact for humans reading the repo, not as the enforcement mechanism.