Read the router (`plugins/poka-yoke/skills/poka-yoke/SKILL.md`) → routed to **`agent-guardrails`**, plus its device templates under `assets/devices/claude-hooks/`.

## The one-sentence diagnosis

Instructions to an agent are **rung zero** — training, not a device. Caps and repetition don't move the rung; they change nothing about enforcement. "Maybe one time in ten" is the signature of a probabilistic rule: it holds while context is short and fails exactly when it matters — long sessions, post-compaction, and subagents that never read your CLAUDE.md at all.

Both rules are irreversible actions, so they need **Control**, not better prose. Here's the replacement.

### 1. Deny rules — `.claude/settings.json`, committed

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

`settings.json`, not `settings.local.json` — a rule on one machine is the same failure as documenting it.

### 2. A hook, because the deny rules leak

Deny entries match the **start** of the command. `git push --force origin main` is caught; `git push origin main --force` is not. And the path denies cover the Edit/Write tools but not `Bash(sed -i src/generated/api.ts)`. Copy `guard_dangerous_commands.py` from this repo into `.claude/hooks/` — it already carries the force-push rule (allowing `--force-with-lease`) — and add one rule for your generated dir:

```python
(r"src/generated/", 
 "src/generated/ is emitted by the codegen step; edits there are overwritten on the next "
 "run and lost. Change the source schema and re-run codegen instead."),
```

Wire it up:

```jsonc
{ "hooks": { "PreToolUse": [ { "matcher": "Bash|Edit|Write",
  "hooks": [{ "type": "command",
    "command": "python3 \"${CLAUDE_PROJECT_DIR}\"/.claude/hooks/guard_dangerous_commands.py" }] } ] } }
```

### 3. The message *is* the device

A bare "denied" produces a creative workaround, often worse. Name what was blocked, why, and the alternative — as above. That's the one place prose belongs.

### 4. Prove it fires

An unverified hook is worse than none — it manufactures confidence. Both directions, each rule:

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main --force"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect: deny + reason
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect: no output
```

### 5. The device that doesn't depend on the harness at all

Force-push's real Control is **server-side branch protection** on your remote. A local hook only protects sessions where it's installed — CI, a teammate's laptop, and a web session all bypass it. Turn that rule on today; the hook is defence in depth.

Then rewrite the CLAUDE.md lines as *facts*, not commands: "`src/generated/` is emitted by `make codegen` from `schema/*.proto`" — that's information the agent needs; "NEVER EDIT" was a rule you were hoping it would follow.

`★ Insight ─────────────────────────────────────`
The tell that you need a device, not better wording, is that you've written the same correction more than once. Second repetition = install something.
Reversibility is the axis for how hard to gate: git makes ordinary edits cheap to undo, so gating them just teaches people to switch the rules off. Aim Control at irreversible and outward-facing only — which both of yours are.
`─────────────────────────────────────────────────`

Neither `src/generated/` nor a `.claude/settings.json` exists in `poke_yoke`, so these rules belong in your other repo. Name it and I'll write the settings file and hook in, then run the verification above.