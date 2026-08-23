Short answer: **nothing is wrong with the wording.** The instruction is rung zero — training, not a device — and 1-in-10 is about what rung-zero enforcement looks like on an agent. Caps and repetition don't change the rung.

## Why it fails ~10% of the time

CLAUDE.md is text the model *reads*; nothing *enforces* it. It drops out under exactly the conditions you'd expect:

- **Context compaction** — long sessions summarize earlier context; the rule may not survive the summary.
- **Subagents** — spawned agents get their own context and often never see the file.
- **Goal pressure** — when a rebase leaves the branch diverged, `--force` is the shortest path to "done," and an agent's prior toward appearing successful wins over a remembered rule.

Shingo's framing: you stopped at "make the operator more careful." The fix is to make the mistake impossible at the tool boundary.

## The devices (Control rung, zero prose)

**1. Deny rules in `.claude/settings.json`** — committed, so they exist for every teammate and every session, not just the machine that set them up:

```jsonc
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

**2. The plugin's PreToolUse hook** for the conditional cases deny patterns miss — e.g. `--force` buried mid-command, or `-f` vs `--force-with-lease`. `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py:31` already handles force-push with a deny *message* that redirects to `--force-with-lease` — that message matters, because a bare "denied" produces a workaround attempt.

**3. Belt-and-suspenders for the irreversible one.** Branch protection on GitHub (disallow force pushes on `main`) catches the case where the agent runs `git` from a subprocess, a different shell, or a harness with no hooks at all. That's the only device that survives "agent found another way to run git."

**4. For `src/generated/`**, add a header to each generated file (`// GENERATED — edit the source at X and run Y`) and a CI check that regeneration produces no diff. The deny rule stops the edit; the header tells the agent *where* to go instead; the CI check catches anything that slips past both.

## Then trim CLAUDE.md

Once these are in, delete the two rules from CLAUDE.md. Leave the *facts* ("generated code comes from `schema.graphql` via `pnpm codegen`") — that's what the agent needs to take the right path when it's blocked from the wrong one.

## Verify before trusting

Run the blocked action and confirm denial + message; run the neighbouring legitimate action (`git push --force-with-lease`, an edit in `src/`) and confirm it still works. Untested hooks fail open — a regex that doesn't match the real command string is protection-shaped nothing.

---

One decision I'd want from you before writing config: should `--force-with-lease` be **allowed** (the template's current stance — safe for personal branches) or **denied too** (stricter; appropriate if the agent shouldn't rewrite any remote history)? Tell me which and I'll draft the `settings.json`, copy the hook into `.claude/hooks/`, and run the verification commands — showing you the config before it lands, since hooks run on your machine on every tool call.