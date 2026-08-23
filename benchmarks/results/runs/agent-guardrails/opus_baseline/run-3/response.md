Nothing about the wording. Caps and repetition are the only levers prose has, and you've pulled both — that's why the failure rate is 1-in-10 rather than 1-in-3. **An instruction in CLAUDE.md is training, and training degrades**: under compaction, in long contexts, and in subagents that never loaded the file. You can't get a rule that's read-and-remembered to 100%. You can get a rule that's *enforced* to 100%.

Your two rules need different devices, and only one of them is a one-liner.

## 1. Generated files — a deny rule is enough

`.claude/settings.json`, committed (not `settings.local.json` — that protects your laptop only, which is the same failure as documenting it):

```jsonc
{
  "permissions": {
    "deny": [
      // poka-yoke: src/generated/ is build output; edits vanish on regen [control]
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)",
      "Bash(git push --force:*)",
      "Bash(git push -f:*)"
    ]
  }
}
```

## 2. Force-push — the deny rule above is a trap on its own

Those two Bash patterns are prefix matches. They catch `git push --force origin main`. They do **not** catch `git push origin main --force`, `git push -f`, or `git push --force-with-lease`'s ugly cousins. A rule that looks enforced and isn't is worse than no rule, because you stop watching for it.

Conditional matching needs a `PreToolUse` hook that inspects the command. This repo already ships one — `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py:31` handles exactly this case, with `--force-with-lease` deliberately left allowed.

## 3. The deny message is the actual device

A bare refusal makes the agent invent a workaround, usually worse. The message is read and acted on, so it has to name what was blocked, why, and the alternative:

> Blocked: edit to `src/generated/user_api.ts`. This directory is build output — your change disappears on the next codegen run. Edit the source schema in `schema/` and run `make codegen`.

That's the one place prose belongs in a guardrail.

## 4. Prove it fires — both directions

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main --force"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect deny + message
echo '{"tool_name":"Bash","tool_input":{"command":"git push --force-with-lease"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect empty (still allowed)
```

Then in a live session, actually ask Claude to force-push and watch it get refused. Untested hooks fail open more often than people expect.

`★ Insight ─────────────────────────────────────`
- Hooks fire on subagent tool calls too. That's likely where a chunk of your 1-in-10 lives — a subagent never read CLAUDE.md.
- Both rules are still *local* devices. The receive-side pair is `git push --force` branch protection on the remote, and a CI job that reruns codegen and fails on a non-empty diff. Those hold even when someone runs Claude with hooks off.
`─────────────────────────────────────────────────`

---

One decision I'd want yours on before writing this: **how does legitimate regeneration get through?** Options are (a) codegen runs via `make codegen`, so `Bash` isn't blocked and only direct `Edit`/`Write` are — simplest, and what the config above does; or (b) an explicit escape hatch the agent can invoke with a stated reason. (b) is more flexible and one rationalization away from useless.

Tell me which, plus the repo path, and I'll write the settings + hook and run the failure test in front of you.