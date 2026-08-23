You aren’t doing anything wrong with the wording. You’re using training to control an operator that sometimes ignores training. Caps and repetition are still rung-zero instructions.

Replace both rules with committed enforcement in `.claude/settings.json`:

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

Force-push also needs a `PreToolUse` hook: permission patterns are prefix matches, so they can miss forms such as `git push origin main --force` or shell-wrapped commands. Use the supplied dangerous-command guard (or equivalent) and give it a useful refusal:

> Blocked: force-push can destroy remote-only commits. Use `--force-with-lease` only with user approval.

For `src/generated/`, the deny rules cover direct editor writes; add a generated-file header that points to the generator/source of truth. If agents can also change files via arbitrary shell commands, use a path-aware `PreToolUse` hook or make that directory read-only in the agent environment—the latter is the true control-level solution.

Put this in committed `.claude/settings.json`, not `settings.local.json`, so every clone gets it. Then prove the device:

- Attempt a force push; confirm it is denied and the message tells Claude what to do.
- Try a normal `git push`; confirm it remains allowed.
- Attempt a direct edit under `src/generated/`; confirm it is denied.
- Edit the generator input or a normal source file; confirm it remains allowed.

Keep `CLAUDE.md` for facts—where generated code comes from, and how to regenerate it—not rules you need the agent to obey.