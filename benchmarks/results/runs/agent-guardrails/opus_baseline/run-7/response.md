`★ Insight ─────────────────────────────────────`
Your CLAUDE.md rules aren't weak — they're the wrong *category* of thing. Caps and repetition can't fix a rung-zero device, because instructions degrade under long context, compaction, and subagents that never read the file at all. The 1-in-10 rate is what "training" looks like, not what "broken prose" looks like.
`─────────────────────────────────────────────────`

Nothing about the wording. Both rules are enforceable at the tool boundary, so stop writing them down and install them.

**1. `src/generated/` — a pure deny rule.** It's path-matchable, so it needs no script. In `.claude/settings.json`:

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

This deliberately does *not* deny Bash, so your codegen command still writes there. That's the distinction that makes the rule survivable — regeneration is legitimate, hand-editing is not.

**2. Force-push — a hook, not a pattern.** A string deny on `git push --force` also kills `--force-with-lease`, which is the safe form you want available. `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py:31` already handles this with a lookahead that permits the lease form. Wire it as a `PreToolUse` hook on `Bash`.

**3. The deny message is the device.** A bare refusal produces a workaround, usually worse. The shipped hook does this for push. For `src/generated/` you'll need to add the message yourself — and that's the piece I can't write, because it has to name *your* regen command.

**4. Commit it.** `.claude/settings.json`, in git — not `settings.local.json`. A rule that lives on one machine has the same failure mode as a rule that lives in prose.

**5. Prove it fires.** Untested hooks fail open more often than people expect:

```
# must deny
git push --force origin feat/x
# must still work
git push --force-with-lease origin feat/x
```
Then try editing a file under `src/generated/` and confirm the block, and confirm an edit in `src/` outside it still goes through.

Then **delete both rules from CLAUDE.md**. Leaving them there teaches you the file is doing work it isn't.

---

**Your turn — one decision I shouldn't make for you.**

The deny reason for `src/generated/` needs a redirect, and the right one depends on your setup. In `.claude/settings.json` I'd add a hook rule; the message should complete: *"Files under `src/generated/` are overwritten by codegen — a hand edit is lost on the next run. Instead: ___"*.

Fill in the blank with your actual regeneration path — `make codegen`? `pnpm gen:types`? edit the `.proto`/schema upstream? The trade-off: naming the command gets the agent unstuck immediately, but if the real fix is usually "change the source schema," naming the command trains it to regenerate over a bug it should have fixed upstream.

Tell me which, and I'll show you the full settings.json before writing anything — hooks run code on your machine on every tool call.