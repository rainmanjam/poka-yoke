You’re not doing anything wrong with the wording. `CLAUDE.md` is training, not enforcement: capitalization and repetition cannot intercept a tool call, and agents can lose or deprioritize those instructions in a long context.

Replace both rules with controls:

```jsonc
// .claude/settings.json — commit this file
{
  "permissions": {
    "deny": [
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)",
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      "Bash(git push --force-with-lease:*)"
    ]
  }
}
```

Use a `PreToolUse` hook as well. Deny patterns only match simple command shapes; the hook should block force-push flags wherever they appear and reject writes to `src/generated/`, with messages such as:

- “Blocked: `src/generated/` is generated output. Change its generator/source and regenerate; do not patch generated files.”
- “Blocked: force-push can destroy remote-only commits. Use a normal push; ask the user before any history rewrite.”

The provided hook template at `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py` already handles force-push variants; extend it for your generated path and register it in committed `.claude/settings.json`.

For defense in depth:

- Put branch protection/rulesets on shared branches that disallow force pushes. That is the server-side control, independent of Claude.
- In CI, regenerate `src/generated/` and fail if it leaves a diff. This prevents a manually edited generated file from merging even if a local guard is bypassed.

Finally, prove each device: attempt a force push and a direct edit to a generated file; confirm denial and its explanatory message. Then confirm an ordinary `git push` and editing the generator source still work. Without that red/green check, a guard can look present while matching nothing.