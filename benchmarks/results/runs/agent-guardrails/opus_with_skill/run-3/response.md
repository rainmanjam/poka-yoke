Read the router and `agent-guardrails` in full, plus the shipped hook template. Also checked: this repo has `.claude/commands/` but **no `.claude/settings.json`** — so both rules currently have zero enforcement anywhere.

## Nothing is wrong with the instructions

The caps aren't underperforming, and neither is the repetition. A line in CLAUDE.md is rung zero — training, not a device. **One-in-ten is the signature of an instruction working exactly as instructions work.** A device is zero-in-ten; it never lands on 90%. The 10% is where the rule wasn't in context at the moment of the action: compaction dropped it, a long session buried it, or a subagent ran that never loaded CLAUDE.md at all. Writing it a third time in caps changes none of those.

Here's the replacement, and the two rules need different devices.

`★ Insight ─────────────────────────────────────`
Deny entries match the **start** of the command string. That single fact decides which of your two rules a pattern can cover and which needs a script — it's the reason `rm -rf` is deliberately absent from this repo's own deny list (`agent-guardrails/SKILL.md:101`).
`─────────────────────────────────────────────────`

### Rule 1 — `src/generated/`: a pattern is enough

```jsonc
// .claude/settings.json
{
  "permissions": {
    "deny": [
      // poka-yoke: generated output is overwritten by codegen; edits here vanish silently
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)",
      "NotebookEdit(./src/generated/**)"
    ]
  }
}
```

Path globs don't have the prefix problem. The gap: `sed -i src/generated/api.ts` and `cat > src/generated/api.ts` go through Bash, not Edit, and walk straight past this. Add a header to the generated files too — belt and braces, and it's the one place prose helps, because the agent reads the file before editing it.

### Rule 2 — force push: a pattern is **not** enough

`"Bash(git push --force:*)"` catches `git push --force origin main` and misses `git push origin main --force` — which is how most people actually type it. It also misses `-f`, and a sloppier pattern would block `--force-with-lease`, the safe form you want to stay available.

This repo already ships the correct regex — `guard_dangerous_commands.py:31`, with the lookahead that spares `--force-with-lease`. Copy it to `.claude/hooks/` in your repo and wire it:

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

### The deny message is the device, not the denial

A bare refusal produces a creative workaround, usually worse. The shipped message names the escape hatch:

> Force-push can destroy commits that exist only on the remote. Use `--force-with-lease` if you must rewrite, and ask the user before rewriting shared history.

### Where it lives

`.claude/settings.json`, **committed**. In `settings.local.json` the rule protects one laptop — the same failure mode as documenting it.

### Prove it fires before you trust it

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main --force"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect: deny + reason

echo '{"tool_name":"Bash","tool_input":{"command":"git push --force-with-lease origin main"}}' \
  | python3 .claude/hooks/guard_dangerous_commands.py   # expect: no output
```

Both directions matter. A regex that doesn't match the real command string is a hook that does nothing while looking like protection — worse than no hook, because it manufactures confidence.

---

**One thing I'd want from you rather than guess at.** The deny message for `src/generated/` has to name the *right* alternative — and that's your domain knowledge, not mine. If it just says "don't edit generated files," the agent will hand-patch the file elsewhere or regenerate wrong. It needs to name your actual regenerate command and the source of truth.

Add a rule to `RULES` in your copy of the script (5-ish lines):

```python
(r"(>|>>|\bsed\s+-i\b.*)\s*\S*src/generated/",
 "src/generated/ is overwritten by <YOUR CODEGEN COMMAND>. "
 "Edit <THE SOURCE: schema.prisma? openapi.yaml?> and re-run it instead."),
```

The trade-off to weigh: scope it too tight and the codegen tool's own writes get blocked; too loose and you're back to a suggestion. Tell me your codegen command and source file and I'll write both files out — I haven't touched anything yet, since hooks execute code on every tool call and that's not a change to make unseen.