You're using a **warning** where you need a **control** — which is exactly the distinction this repo is built around.

## The diagnosis

CLAUDE.md is text in a context window. It competes with the conversation, the file contents, the tool results, and every other instruction in the file. Compliance with text guidance is probabilistic by construction, and ~90% is roughly what warning-level controls get in any system, human or model. Caps and repetition don't move that number, because the failure isn't "didn't understand" — it's "attention got outcompeted mid-task." A model that has just spent 40k tokens on a refactor and needs a clean push is not re-reading line 12 of your CLAUDE.md.

Repetition also has a cost: it lengthens the file, and a long CLAUDE.md dilutes the priority of *everything* in it. You made the other rules slightly weaker to make these two rules no stronger.

`★ Insight ─────────────────────────────────────`
Shingo's control hierarchy: **elimination** (make it impossible) > **prevention/control** (block at execution) > **warning** (tell someone) > **detection** (find out after). CLAUDE.md is a warning. A `PreToolUse` hook is a control — it runs in the harness, outside the model's attention, and has a 100% hit rate because it's a regex, not a judgment call.
`─────────────────────────────────────────────────`

## The fix

You already shipped the device — it's sitting unwired at `plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py`. Line 31 already denies force-push (allowing `--force-with-lease`). What it doesn't have is a write-path guard for generated directories; `PROTECTED_PATHS` (line 82) only covers secrets.

Two rules, two different hazard shapes, so two different checks:

| Rule | Surface | Device |
|---|---|---|
| never force push | `Bash` command string | regex deny — already written |
| never edit `src/generated/` | `Edit`/`Write` `file_path` | path deny — needs adding |

Worth noting what the hook does *not* cover: it only constrains this agent. A human, a different tool, or CI can still force-push. If that matters, the durable version is branch protection on the remote (elimination — the server refuses) plus a pre-commit hook for the generated dir. The Claude hook is the fast layer, not the only one.

One more thing your own script gets right and is worth preserving when you extend it: the deny **reason** is the device (line 13–15). A bare "denied" makes the agent invent a workaround, often worse than the original command.

## Where I need your call

The `src/generated/` guard has a real design decision in it: **what happens when regeneration is legitimate?** If the codegen tool runs via `Bash` it sidesteps a path-based Edit/Write guard entirely — which may be exactly right, or may be a hole. The options:

- **Hard deny, no exceptions** — regeneration must run as a Bash codegen command, never a hand-edit. Cleanest, but breaks if your codegen is ever wrapped in a script the agent writes.
- **Deny with a named escape hatch** — e.g. allow if the commit is tagged, or if an env var is set for that invocation. More flexible, and every escape hatch eventually gets used casually.
- **Deny writes, allow reads** — the agent can still learn from generated code, just not modify it.

I'd default to the third combined with the first: read-only, hard deny on write, regeneration happens through the codegen command. But you know whether your codegen is ever agent-invoked.

Tell me which, and whether you want me to wire this into `.claude/settings.json` for this repo or globally — I'll add the `PROTECTED_PATHS` sibling rule and the settings block.