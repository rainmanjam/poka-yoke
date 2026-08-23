Nothing is wrong with your wording. The problem is that CLAUDE.md is the wrong tool: it's an instruction, and instructions hold ~90% of the time regardless of caps or repetition — long contexts, compaction, and subagents that never read the file all erode them. One-in-ten is what a good instruction looks like. To get to zero you need a device that runs before the tool call, not prose the model is supposed to remember.

Here is the replacement for both rules. I haven't written anything — hooks run on your machine on every tool call, so look first.

**1. Force push → a deny rule (string match is enough)**

`.claude/settings.json` (committed, so it protects every clone, not just yours):

```jsonc
{
  "permissions": {
    "deny": [
      // poka-yoke: force-push rewrites shared history; irreversible
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      "Bash(git push --force-with-lease:*)"
    ]
  }
}
```

Drop the third if you actually want `--force-with-lease` allowed — it's the safe variant.

**2. `src/generated/` → deny rules for the edit tools, plus a hook for the shell**

```jsonc
"deny": [
  // poka-yoke: generated files are overwritten on next build; edit the source instead
  "Edit(./src/generated/**)",
  "Write(./src/generated/**)",
  "MultiEdit(./src/generated/**)"
]
```

That closes the tool path, but `sed -i`, `cat >`, `mv` through Bash still get through. That's conditional (depends on the path inside an arbitrary command), so it needs a `PreToolUse` hook on `Bash` that scans the command for `src/generated/` and returns a deny. There are templates in `~/.claude/plugins/cache/poka-yoke/poka-yoke/0.1.0/assets/devices/claude-hooks/`.

**3. The deny message matters more than the deny.** The agent reads it and acts on it. A bare refusal produces a workaround (often `sed`). Write it like an error message for a colleague:

> Blocked: edit to `src/generated/`. These files are regenerated from `schema/*.graphql` by `npm run codegen`; edit the schema and re-run codegen instead.

Same for force push: name the alternative (`git push --force-with-lease` or "ask the user").

**4. Prove it fires.** Ask Claude to force push and to edit a generated file; confirm the denial and that the message shows. Then do a normal `git push` and a normal edit and confirm those still work. A regex that doesn't match the real command string is a hook that looks like protection and isn't — that's worse than nothing.

**5. Then delete the CLAUDE.md lines.** Keep the *fact* ("`src/generated/` is produced by `npm run codegen` from `schema/`") and drop the *command*. What stays in CLAUDE.md should be things the agent needs to know, not things you hope it remembers.

If you want, I can draft the settings.json and the Bash hook and show you the diff before writing — and then run the blocked/allowed pair to verify.