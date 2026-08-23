Nothing about the wording. Caps and repetition are the two knobs that don't exist — CLAUDE.md is training, and training degrades. That's exactly the 1-in-10 shape: long context dilutes it, compaction drops it, and subagents often never see it at all. Repeating it twice just spends tokens on the same rung.

`★ Insight ─────────────────────────────────────`
Your two rules need *different* devices. "Don't edit src/generated/" is a pure path predicate — a permission rule decides it with no logic. "Never force push" is conditional (`--force-with-lease` is the safe form you want to keep) — that needs a hook that inspects the command.
`─────────────────────────────────────────────────`

## 1. The deny rules — `.claude/settings.json`, committed

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

Committed, not `settings.local.json` — a rule on one machine is the same failure as documenting it.

## 2. The hook, for what patterns can't catch

Deny rules match strings, so `git push origin +main` and `git push --force-with-lease` are both indistinguishable-or-invisible to them. This repo already ships the guard: `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py:31` has the force-push rule with the lookahead that keeps `--force-with-lease` allowed. Wire it as a `PreToolUse` hook on `Bash|Edit|Write`.

For `src/generated/`, the hole the deny rule leaves is Bash — `sed -i`, `>` redirects, a codegen script writing by hand. Add a path rule to that hook's `PROTECTED_PATHS`.

## 3. What it says when it fires — this is the part that decides the outcome

`permissions.deny` returns a bare refusal, and a bare refusal is what produces the creative workaround. The hook's `permissionDecisionReason` is your only channel to redirect:

> Blocked: `src/generated/` is written by `make codegen`. An edit here is overwritten on the next build, silently. Change the schema in `src/schema/` and regenerate.

## 4. The backstop that doesn't depend on the runtime

Deny rules protect Claude Code only. A pre-commit hook rejecting a diff that touches `src/generated/` without a matching schema change, plus the same check in CI, protects every agent and every human.

## 5. Prove it fails

```bash
git push --force-with-lease   # must still work
git push --force              # must be denied, with the message
```

An untested hook whose regex doesn't match the real command string does nothing while looking like protection — worse than none, because it buys confidence.

---

Two things I need from you before writing anything: **which repo** (there's no `src/generated/` here in poke_yoke), and **is `--force-with-lease` allowed** on your team, or is all history rewriting off-limits? That second answer changes the regex, and it's a call about your workflow, not mine. Tell me both and I'll show you the exact diff before it lands.