Using **poka-yoke-agent-guardrails** (routed from the poka-yoke router).

## Nothing is wrong with the instructions. The problem is that they're instructions.

In Shingo's ladder, a line in CLAUDE.md is **rung zero** — training, not a device. Caps don't raise the rung. Repeating it twice doesn't raise the rung. Both changes operate on *emphasis*, and emphasis is a property of training. Training degrades; devices don't.

Your 1-in-10 number is the diagnostic. That's not a wording defect — it's the characteristic failure curve of a rung-0 control. It fails when context is compacted, when the relevant CLAUDE.md is out of scope, when a subagent runs that never read the file, and when a plausible local goal ("the remote rejected my push") outranks a remembered rule.

`★ Insight ─────────────────────────────────────`
**9/10 is worse than 0/10.** A rule that fails every time gets replaced. A rule that works 90% of the time earns trust, so you stop watching — and the 10% lands unobserved. Partial compliance is what keeps rung-0 controls installed.
**Repetition is a tell.** The skill's own rule: *"If you have been repeating the same correction to an agent, that is the signal to stop writing instructions and install a device."* You wrote it twice in the file — same signal.
`─────────────────────────────────────────────────`

## Your two rules are different hazards and need different devices

**`never force push`** — irreversible and outward-facing. This is the only class where Control is mandatory.

- `.claude/settings.json` → `"deny": ["Bash(git push --force:*)", "Bash(git push -f:*)"]`
- **Plus GitHub branch protection.** The deny rule protects you from the agent; branch protection protects the branch from everyone, including you, CI, and any other agent on any other machine. Server-side is a strictly higher rung than client-side.

**`never edit files in src/generated/`** — reversible, so a hard deny is the wrong instinct. Aim for contact + detection:

- Deny rule on `Edit(./src/generated/**)`
- A header in each generated file (`// GENERATED — edits are overwritten by \`make codegen\``)
- A CI check that regenerates and fails on any diff. This is the real device: it makes the edit *pointless* rather than merely forbidden, and it catches the human doing it too.

The deny message matters more than the deny. A bare "denied" makes the agent invent a workaround — often worse. `guard_dangerous_commands.py` in this repo already covers the force-push case with a reason pointing at `--force-with-lease`.

## One decision I'd want from you before installing

There's a genuine trade-off in the force-push rule: `--force-with-lease` on your *own* unshared feature branch is legitimate and common. Blocking it too makes the agent fight the harness, which is how guardrails get switched off.

Do you want (a) hard deny on all force variants, or (b) allow `--force-with-lease`, deny bare `--force`/`-f`?

Tell me which, and point me at the repo (this one, or another?), and I'll show you the exact `settings.json` before writing anything.