I have what I need. Here's the answer, following the skill.

## Nothing is wrong with your instructions. Instructions are the wrong tool.

A line in CLAUDE.md — caps, repeated, whatever — is training, not enforcement. It degrades exactly the way you're seeing: after context compaction, in long sessions, and in subagents that never load the file at all. "One time in ten" is the normal failure rate of a rule that exists only as text. The fix is to move both rules out of prose and into something that runs *before* the tool call executes.

Here's the complete replacement, in five parts.

### 1. Deny rules — covers force-push

In `.claude/settings.json` (the committed one, see §4):

```jsonc
{
  "permissions": {
    "deny": [
      "Bash(git push --force:*)",   // poka-yoke: force-push destroys remote-only commits
      "Bash(git push -f:*)",
      "Edit(./src/generated/**)",    // poka-yoke: generated files are overwritten on next build
      "Write(./src/generated/**)",
      "MultiEdit(./src/generated/**)"
    ]
  }
}
```

Deny rules match the **prefix** of the command, so `git push origin main --force` slips past `Bash(git push --force:*)`. That's why force-push needs the hook too.

### 2. A PreToolUse hook — covers the cases patterns can't

Copy `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py` to `.claude/hooks/`. Its force-push regex already handles flag-anywhere ordering and keeps `--force-with-lease` allowed. Add one rule for your generated directory, which also catches `sed -i`, `cp`, `>` redirects — anything Bash can do to those files that `Edit(...)` deny rules can't see:

```python
(r"src/generated/",
 "src/generated/ is build output; edits there are overwritten on the next codegen run. "
 "Change the source (schema/*.proto, openapi.yaml, etc.) and re-run the generator instead."),
```

Wire it in the same `settings.json`:

```jsonc
"hooks": {
  "PreToolUse": [{
    "matcher": "Bash|Edit|Write|MultiEdit",
    "hooks": [{ "type": "command",
                "command": "python3 \"${CLAUDE_PROJECT_DIR}\"/.claude/hooks/guard_dangerous_commands.py" }]
  }]
}
```

### 3. The deny message is the actual device

The agent reads the refusal and acts on it. A bare "denied" produces a workaround — often `cat > file` or `--force-with-lease` when it shouldn't. The message must say **what** was blocked, **why**, and **what to do instead** — as in the rule above. This is the one place prose belongs.

Also put a header in the generated files themselves (`// GENERATED — do not edit; source: X`). The agent sees that when it reads the file, before it ever reaches for Edit.

### 4. Where it lives

`.claude/settings.json`, committed. `settings.local.json` protects one laptop, which is your current failure in a different costume.

### 5. Prove it fires

Untested hooks fail open. Before you trust it:
- Ask Claude to force-push → expect the denial *and* the message.
- Ask it to run `git push --force-with-lease` → should still work.
- Ask it to fix a typo in `src/generated/foo.ts` → expect the denial pointing at the source file.
- Ask it to edit `src/generators/foo.ts` (the near-miss) → should work.

★ Insight ─────────────────────────────────────
- Deny rules and hooks are Shingo's *control* rung: the mistake can't happen. CLAUDE.md is rung 0. No amount of emphasis moves prose up the ladder.
- "Edit" denies don't see Bash. The hook's Bash rule is what closes the `sed -i` / `echo >` gap — test that path specifically.
- The deny reason is read by a model, not a human. Write it as a redirect, not a refusal.
─────────────────────────────────────────────────

**Recap:** Your instructions aren't badly written — they're the wrong rung. Install the two deny rules plus the hook above in committed `.claude/settings.json`, give each a redirecting deny message, and run the four-test check. Once that's in, delete the caps lines from CLAUDE.md and replace them with the *fact*: "src/generated/ is produced by `make codegen` from X." I can write the settings file and hook into this repo if you want, but hooks execute on your machine on every tool call, so I'd rather you see the config first.