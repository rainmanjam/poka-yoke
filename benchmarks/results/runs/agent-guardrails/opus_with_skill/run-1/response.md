Following `poka-yoke:agent-guardrails`.

## The diagnosis, in one sentence

Instructions to an agent are rung zero — a device, not a rule, is what stops this. Caps and repetition don't raise the rung; the 1-in-10 is what rung zero looks like when context gets long, compaction drops the middle of the file, or a subagent runs that never read CLAUDE.md at all.

## Your two rules need different devices

**`src/generated/` is pattern-shaped.** A deny rule covers the Edit path today:

```jsonc
// .claude/settings.json  — committed, not settings.local.json
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

**Force-push is not.** Deny entries match the *start* of the command, so `"Bash(git push --force:*)"` misses `git push origin main --force`, and blocking the whole prefix would also kill `--force-with-lease`, which is the form you want kept. That needs a `PreToolUse` hook. The same hook closes the Bash escape on `src/generated/` — `sed -i src/generated/api.ts` and `> src/generated/api.ts` sail straight past an `Edit()` deny.

The plugin already ships the script: `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py:31` has the force-push rule with the lookahead that keeps `--force-with-lease` alive. Copy it to `.claude/hooks/` in the target repo and wire it with `matcher: "Bash|Edit|Write|Read"`.

**The deny message is the device, not the denial.** A bare refusal makes the agent invent a workaround, usually worse. Yours should read like:

> Blocked: `src/generated/` is emitted by `npm run codegen`. Edits here are erased on the next build. Change the schema in `src/schema/` and re-run codegen.

Add the same sentence as a header comment in the generated files — that catches the agent at read time, before it forms the intent.

**Then prove it fires**, or you have confidence without protection:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main --force"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect: deny
echo '{"tool_name":"Bash","tool_input":{"command":"git push --force-with-lease"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect: no output
```

`★ Insight ─────────────────────────────────────`
A deny rule that has never gone red is a rumour, not a device — an unmatched regex looks identical to a working one from the outside.
The 1-in-10 rate is the tell: a rule obeyed 90% of the time is a rule with no enforcement, not a rule that needs stronger wording.
`─────────────────────────────────────────────────`

## One decision that's yours

Blocking Bash writes into `src/generated/` also blocks your codegen script, since that's a Bash command writing to that path. Two ways out, and the right one depends on your setup: allowlist the exact regen command (`npm run codegen`) before the path check, or only deny in-place editors (`sed -i`, `>`, `tee`) and let anything else through. The first is tighter; the second doesn't break when you rename the script.

Tell me which repo this is and which you want, and I'll write the config and the hook, run both proof cases, and show you the diff before anything lands.