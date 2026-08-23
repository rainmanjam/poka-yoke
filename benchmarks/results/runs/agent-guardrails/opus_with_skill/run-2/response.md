I read the router and it points this at `agent-guardrails` — "CLAUDE.md says X but it still does Y" is its exact trigger. Here's what it says, applied to your two rules.

## The diagnosis, in one sentence

Nothing is wrong with your prose — **instructions to an agent are rung zero.** Caps and repetition don't change that; they're training, and training degrades under long contexts, compaction, and subagents that never read your CLAUDE.md. One-in-ten *is* what a well-written instruction looks like. The fix is a device, not better wording.

Your two rules need different devices, and it's worth knowing why.

## Rule 1 — `src/generated/` — a deny rule is enough

Pure path match, no logic. In `.claude/settings.json`:

```jsonc
{
  "permissions": {
    "deny": [
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)"
    ]
  }
}
```

Gap to know about: this covers the Edit/Write tools, not a Bash-mediated write (`sed -i src/generated/...`). Close that with a header in each generated file plus a CI check that regeneration produces no diff — Detection, but the file is reversible so it doesn't need Control.

## Rule 2 — force push — needs a hook

Deny entries match the **start** of the command. `Bash(git push --force:*)` catches `git push --force origin main` and misses `git push origin main --force`, which is the form that will bite you. Add the prefix denies anyway, then wire the shipped guard for real coverage:

```jsonc
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash|Edit|Write|Read",
      "hooks": [{
        "type": "command",
        "command": "python3 \"${CLAUDE_PROJECT_DIR}\"/.claude/hooks/guard_dangerous_commands.py"
      }]
    }]
  }
}
```

Copy `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py` into `.claude/hooks/`. Its regex is `\bgit\s+push\b.*(--force(?!-with-lease)|...-f...)` — flag anywhere, and `--force-with-lease` stays allowed.

## The part people drop: the message

The agent reads the denial and acts on it, so a bare refusal produces a creative workaround. The shipped reason says *"Force-push can destroy commits that exist only on the remote. Use `--force-with-lease` if you must rewrite, and ask the user before rewriting shared history."* Write yours for `src/generated/` the same way — name the codegen command it should run instead.

## Where it lives

`.claude/settings.json`, **committed**. In `settings.local.json` it protects one machine, which is the same failure mode as documenting it.

## Verify — I could not run this here

This session has no exec permission, so I did not test the guard; do this before trusting it:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main --force"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect: deny + --force-with-lease
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect: silence
```

An unverified hook is worse than none — a regex that doesn't match the real command string does nothing while looking like protection.

`★ Insight ─────────────────────────────────────`
The interesting split here isn't force-push vs. generated files, it's **irreversible vs. reversible**. Force-push destroys remote-only commits — Control, no exceptions. A stray edit to `src/generated/` is one `git checkout` away from fixed, so it earns a deny rule and a CI check but not a hook.
`─────────────────────────────────────────────────`

Want me to write both files into this repo (or point me at the target repo)? One decision shapes the deny message: **what's the legitimate regeneration command for `src/generated/`?** The message should name it, so the agent runs that instead of hand-editing — that redirect is what turns a blocked call into the right one.