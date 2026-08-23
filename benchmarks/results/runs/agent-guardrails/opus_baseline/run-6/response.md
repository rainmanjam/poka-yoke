Nothing's wrong with your prose. The problem is that it's prose.

`★ Insight ─────────────────────────────────────`
CLAUDE.md is **rung zero** on your own ladder — training, not a device. It degrades exactly where you'd want it strongest: after compaction, in long contexts, and in subagents that never read the file. Caps and repetition don't change the rung; they just make a rule *feel* enforced. One-in-ten is the expected failure rate of a remembered rule, not a sign you wrote it badly.
`─────────────────────────────────────────────────`

## The replacement

**1. Deny rules — free, no scripting.** In `.claude/settings.json`:

```json
{
  "permissions": {
    "deny": [
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)"
    ]
  }
}
```

**2. But neither of your rules is fully pattern-matchable — both need a hook.** Deny rules are prefix matches, so they leak in two ways you'll hit in practice:

- `git push origin main --force` — flag isn't adjacent, no match. And a naive pattern also blocks `--force-with-lease`, which is the *safe* form you want to keep.
- `python codegen.py > src/generated/api.ts` — that's a Bash write, not an `Edit`, so the path deny never sees it.

You already ship the fix: `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py:31` handles force-push with the `--force-with-lease` lookahead. Copy it to `.claude/hooks/` in the target repo and wire it per `README.md:49`, then add a generated-files rule to `RULES`.

**3. The deny message is the device.** A bare refusal makes the agent improvise a worse route (`git push` → delete branch → recreate). Write it for a colleague:

> Blocked: edit to `src/generated/`. These files are regenerated from `schema.graphql` and your change will be silently overwritten on the next build. Edit the source schema and run `make generate`.

**4. Commit it.** `.claude/settings.json`, not `settings.local.json` — a rule that lives on one machine has the same failure mode as documenting it.

**5. Prove it fires.** Run `git push --force` (must deny, with the message), then `git push --force-with-lease` (must still work). Then `echo x > src/generated/t.ts` and `echo x > src/t.ts`. An untested hook fails open more often than you'd think — a regex that misses the real command string is protection that isn't there.

---

Two notes on this repo specifically: `src/generated/` doesn't exist here, so I've written the above for whichever repo you meant — say which and I'll wire it up concretely. And `poke_yoke` itself has `.claude/commands/` but no `settings.json`, so it currently has zero of these devices installed. Also `guard_dangerous_commands.py:4` points at a `hooks.json` "in this directory" that doesn't exist — the wiring actually lives in `README.md`.

**One thing worth your call rather than mine:** the deny messages. I can write generic ones, but you know what the agent *should* do instead in your repo — the codegen command, whether force-push-to-a-feature-branch is fine. Want to draft the two message strings and I'll install the rest?