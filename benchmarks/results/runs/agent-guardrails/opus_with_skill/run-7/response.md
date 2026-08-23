I couldn't run the hook test here (the sandbox blocked both the shell loop and the temp file write), so the verification commands below are yours to run — I've flagged that rather than claiming I proved it.

## What you're doing wrong

Nothing, in the prose. Caps and repetition don't change the *rung* — a line in CLAUDE.md is training, and training degrades under long contexts, compaction, and subagents that never read the file. "Maybe one time in ten" is the expected yield of rung-zero controls, not a sign you phrased it badly. Writing it twice in caps is the signal to stop editing the file and install a device.

Your two rules need *different* devices, and that's the part worth getting right.

## 1. `src/generated/` → deny rule (path match is enough)

`.claude/settings.json`, **committed** — in `settings.local.json` it protects one machine, which is the same failure as documenting it. You currently have no `settings.json` at all.

```jsonc
{
  "permissions": {
    "deny": [
      // poka-yoke: generated files are rewritten by codegen; edits here vanish silently [control]
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)",
      "Bash(git push --force:*)",
      "Bash(git push -f:*)"
    ]
  }
}
```

## 2. Force-push → the deny rule is not enough

**A deny entry matches the *start* of the command.** So those two entries catch `git push --force origin main` and miss `git push origin main --force`, `git push -f`, and `cd sub && git push --force`. Same gap on the generated dir: the deny covers the `Edit`/`Write` tools, not `sed -i ... src/generated/api.ts` through Bash. Both leftovers are conditional, so they need a `PreToolUse` hook that inspects the call.

`.claude/hooks/guard.py` — adapted from `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py`:

```python
RULES = [
    # --force-with-lease is the safe form, so the lookahead sits right after --force
    (r"\bgit\s+push\b.*(--force(?!-with-lease)|(?<![\w-])-f(?![\w-]))",
     "Force-push can destroy commits that exist only on the remote. Use "
     "--force-with-lease, and ask before rewriting shared history."),
    (r"src/generated/",
     "src/generated/ is codegen output — edits are silently overwritten on the "
     "next build. Change the source schema and regenerate instead."),
]
```

Wired in the same `settings.json`:

```jsonc
"hooks": {
  "PreToolUse": [{
    "matcher": "Bash|Edit|Write",
    "hooks": [{ "type": "command",
      "command": "python3 \"${CLAUDE_PROJECT_DIR}\"/.claude/hooks/guard.py" }]
  }]
}
```

`★ Insight ─────────────────────────────────────`
**The deny message is the device, not the denial.** A bare "denied" makes the agent invent a workaround — often worse than the original command. The message is the one place prose legitimately belongs, because the agent reads it and acts on it.
**Fail open on bad input.** A hook that crashes on an unusual payload blocks *all* tool use — that's your outage, not your protection.
`─────────────────────────────────────────────────`

## 3. Prove it fires — before you trust it

An unverified hook is worse than none; it creates confidence without protection. Run all four:

```bash
cd .claude/hooks
echo '{"tool_name":"Bash","tool_input":{"command":"git push origin main --force"}}' | python3 guard.py   # expect: deny
echo '{"tool_name":"Bash","tool_input":{"command":"git push --force-with-lease origin x"}}' | python3 guard.py  # expect: empty
echo '{"tool_name":"Edit","tool_input":{"file_path":"src/generated/api.ts"}}' | python3 guard.py       # expect: deny
echo '{"tool_name":"Edit","tool_input":{"file_path":"src/api.ts"}}' | python3 guard.py                 # expect: empty
```

The two "expect: empty" cases matter as much as the denials — that's what keeps you from turning the rules off in a week.

## 4. The rung above all of this

Force-push has a **remote-side** device: branch protection on `main`. That holds no matter who pushes — this agent, another agent, a subagent, you at 2am. The hook protects one harness; branch protection protects the branch. Do both; if you only do one, do this one.

For `src/generated/`, the equivalent backstop is a CI job that regenerates and fails on a non-empty diff — it catches the edit even when it arrives by a route neither device covers.

---

**One thing I'd want from you before writing any of it:** the deny message for `src/generated/` needs the *actual* alternative — "edit `schema.prisma` and run `pnpm gen`", or whatever your codegen entry point is. That sentence is the difference between the agent doing the right thing and the agent creatively editing the file some other way. Tell me the source-of-truth file and the regen command, and confirm you want me to write `.claude/settings.json` and `.claude/hooks/guard.py` — hooks execute code on your machine on every tool call, so I won't install them unseen.