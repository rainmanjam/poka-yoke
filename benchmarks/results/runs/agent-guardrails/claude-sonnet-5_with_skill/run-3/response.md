**The insight:** what you're seeing isn't a bug in your prose, it's what rung-zero training does under load. "Never do X" in CLAUDE.md is an instruction, not a device — it gets deprioritized under long contexts, dropped across `/compact`, and is easy for the model to just not carry into whatever subagent actually issues the risky command. "One time in ten" is exactly the failure signature of something that *usually* gets read and *occasionally* doesn't — caps and repetition don't change that, because the mechanism that's failing (attention over prose) is the same one you're doubling down on.

The fix is a `PreToolUse` deny that runs before the tool executes, not text the model has to remember to obey. That's five pieces, not one — here's each for your two rules:

**1. The deny rule** — `.claude/settings.json`:
```jsonc
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

**2. Where a pattern isn't enough** — deny rules match string prefixes, so they miss variants: `git push origin +main` (the `+` syntax for force), `git push --force-with-lease=refs/heads/main:...`, or a shell one-liner that writes into `src/generated/` via `Bash` (`cp foo.ts src/generated/`, `sed -i ... src/generated/x.ts`, a codegen script's output redirected there) — none of those are caught by `Edit`/`Write` denies, because the write happens inside a shell command, not a tool call the permission layer inspects by path. Those need a `PreToolUse` hook on `Bash` that regex-checks the command string for `push.*(force|-f\b|\+[\w/-]+:)` and for any write-shaped command (`>`, `cp`, `mv`, `sed -i`, `tee`) targeting `src/generated/`.

**3. The deny message** — an agent that hits a bare "denied" will often just try a different command to get the same result. Make the message redirect it:
> Blocked: `src/generated/` is generated output, not source — edits here are discarded on the next codegen run. If the generated content is wrong, fix the generator/schema it's produced from instead.
> Blocked: force-push rewrites shared history. If you need to fix the last commit, ask the user to confirm and push it themselves, or use a new commit.

**4. Where it lives** — `.claude/settings.json`, committed to the repo (not `settings.local.json`, which only protects your machine).

**5. Proof it fires** — before trusting it, actually run the blocked action and confirm you get the deny + message, then run a legitimate neighboring action (editing a normal `src/` file, a normal non-force push) and confirm it still works. An unverified hook is worse than none — a regex that doesn't match the real command string looks like protection and provides zero.

I found no `.claude/settings.json` in this repo yet, so none of this is installed currently — that alone would explain 100% noncompliance, not 90%. Want me to write the deny rules and a `PreToolUse` guard hook for the `src/generated/` shell-write case, then walk through steps 5's verification with you before you trust it?