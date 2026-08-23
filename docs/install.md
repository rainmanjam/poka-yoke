# Installing

poka-yoke ships to 19 runtimes from one set of skills. Ten have a native manifest in the
repository, so on most of them installation is "point the runtime at this repo" rather than
"copy files and rewrite paths".

Earlier versions of this page told you to vendor the directory and rewrite
`${CLAUDE_PLUGIN_ROOT}` to wherever you put it. That step is gone: skills now reference
bundled files relative to themselves, and the detector is invoked by a path relative to the
skill that names it. Both changes are enforced by `tests/test_portability.py`, so they
cannot quietly come back.

## Support tiers, stated honestly

| Tier | What it means | Runtimes |
|---|---|---|
| **Benchmarked** | Skills load and route; measured against a no-skill baseline | Claude Code, Codex, Antigravity |
| **Native manifest** | Ships a manifest the runtime understands; structurally verified in CI, but not behaviourally tested by us | Cursor, Devin, Kimi, Hermes, Gemini CLI, Grok, Qoder, Kiro |
| **Instruction file** | Works via a pointer in the runtime's context file | Copilot, Windsurf, Cline, Junie, Zed, Aider |
| **Vendored** | No manifest while npm is on hold, copy `plugins/poka-yoke/` and point the runtime at the skills directory | opencode, Pi |

**Three runtimes are benchmarked; the rest are structurally verified only.** Claude Code,
Codex has been run through the same thirteen scenarios and Antigravity through twelve of
them, `audit` being unrunnable there, blind-graded
against the same assertions, see [the generated report](../benchmarks/results/benchmark.md) for the counts,
which are generated and therefore current. Claude Code's manifest is the source of truth and
the others are generated from it, so CI fails the moment one drifts, but a manifest that
parses is not a runtime that behaves. Treat everything outside those three as structurally
correct and behaviourally unverified. If you run poka-yoke on one of them, a session
transcript in an issue is the most useful thing you can send.

> **`audit` does not work on Antigravity.** That skill invokes the bundled detector, and `agy`
> in print mode refuses to execute a command in every permission mode it offers, `--mode plan`
> and `--mode accept-edits` both fail with a permission error, and `--sandbox` denies file
> reads as well. Only `--dangerously-skip-permissions` runs commands, and it grants writes with
> them. There is no exec-without-write setting.
> The other ten skills run normally. Any runtime that blocks command execution will hit this.

---

## Claude Code

```
/plugin marketplace add rainmanjam/poka-yoke
/plugin install poka-yoke@poka-yoke
```

Invoke a mode directly with `/poka-yoke:audit`, `/poka-yoke:design`, and so on, or ask by
name, "poka-yoke this repo", "mistake-proof this API".

**Without the marketplace**, copy the skills in. No path rewriting is needed any more:

```bash
git clone https://github.com/rainmanjam/poka-yoke /tmp/pk
mkdir -p ~/.claude/skills
cp -r /tmp/pk/plugins/poka-yoke/skills/* ~/.claude/skills/
cp -r /tmp/pk/plugins/poka-yoke/{references,scripts,assets} ~/.claude/
```

The second `cp` is not optional and its destination is not a typo. Every SKILL.md reaches
its references, scripts and assets at `../../`, which is the directory holding `skills/`, so the other three have to land beside `skills/` rather than inside it.

Use `.claude/skills/` instead of `~/.claude/skills/` to commit it for the whole team, and
`.claude/` instead of `~/.claude/` in the second `cp` so the pair still lines up.

## Codex, Copilot CLI, Gemini CLI, via `~/.agents/skills/`

These runtimes all read a shared cross-runtime skills directory, which is the least
duplicated way to install once and get all three:

```bash
git clone https://github.com/rainmanjam/poka-yoke /tmp/pk
mkdir -p ~/.agents/skills
cp -r /tmp/pk/plugins/poka-yoke/skills/* ~/.agents/skills/
cp -r /tmp/pk/plugins/poka-yoke/{references,scripts,assets} ~/.agents/
```

Same rule as above: the skills resolve their bundled files at `../../`, so `references/`,
`scripts/` and `assets/` sit beside `skills/` rather than under it.

Codex also reads `.codex-plugin/plugin.json` from a plugin checkout, and Gemini CLI reads
`gemini-extension.json` with `GEMINI.md` as its context file. Both are in this repo.

Copilot is in the instruction-file tier of the table above because only the CLI reads
`~/.agents/skills/`; the IDE extension reads `.github/copilot-instructions.md`, the pointer
file this repo ships.

For subagent-based auditing, Codex needs multi-agent enabled in `~/.codex/config.toml`:

```toml
[features]
multi_agent = true
```

## Cursor

The repository ships `.cursor-plugin/plugin.json`. For a project-scoped install without the
plugin system, vendor the skills and add a rule. Leave `globs` out: a rule with globs
attaches whenever a matching file is in context, and poka-yoke is meant to be asked for,
not injected into every edit. Without them Cursor selects the rule by its `description`, so
keep that line specific, because it is the trigger:

```mdc
---
description: Mistake-proofing: audit for footguns, design APIs that resist misuse, install guardrails, prevent incident recurrence
alwaysApply: false
---

Read `.cursor/poka-yoke/skills/poka-yoke/SKILL.md` and follow its routing.
```

Save as `.cursor/rules/poka-yoke.mdc`.

## Devin, Kimi, Hermes, opencode, Pi

Devin, Kimi and Hermes each have a manifest in the repo (`.devin-plugin/`, `.kimi-plugin/`,
`.hermes-plugin/`), point the runtime at this checkout.

Pi reads `pi.skills` from a `package.json`. That package is not published while npm is on
hold, which costs opencode its declarative install too. Vendor `plugins/poka-yoke/` and
point either runtime at the skills directory instead.

No runtime glue script is required on any of them. Frameworks that force a bootstrap into
every session need an extension to inject it; poka-yoke is invoked deliberately, so
declaring where the skills live is the entire integration.

## Antigravity (`agy`)

Reads `AGENTS.md`, which is in this repo. Benchmarked, see the cross-runtime table in the
[README](../README.md#does-it-work-outside-claude-code). Three runtime-specific notes:

- **`audit` will not run.** No permission mode `agy` offers executes the detector without also granting writes; use `/poka-yoke:design`
  and the other nine skills, or run the detector yourself and paste the output.

- Subagents are `invoke_subagent`: `TypeName: "research"` for a read-only audit, `"self"`
  when the run will apply fixes.
- There is no todo tool. Where a skill asks for a task list, write a **task artifact**: `write_to_file` with `IsArtifact: true` and `ArtifactMetadata.ArtifactType: "task"`, and
  edit it as you go. `manage_task` manages background processes, not checklists.

## Windsurf, Cline, Junie, Zed, Aider, and anything with a context file

Vendor `plugins/poka-yoke/skills/` and add a pointer **with the trigger conditions**: a
pointer without them never fires. This repo's own pointer files
(`.windsurfrules`, `.clinerules`, `.junie/guidelines.md`) show the shape.

## Claude Agent SDK

```python
from claude_agent_sdk import ClaudeAgentOptions

options = ClaudeAgentOptions(setting_sources=["project"])   # reads .claude/skills/
```

Or load one `SKILL.md` as a system prompt fragment when you want a single mode. The router
is `skills/poka-yoke/SKILL.md`.

## No agent at all

The references are written to be read by people:

- [`hazard-catalog.md`](../plugins/poka-yoke/references/hazard-catalog.md), 28 hazard shapes with devices
- [`ux-patterns.md`](../plugins/poka-yoke/references/ux-patterns.md), interface devices by consequence
- [`method.md`](method.md): the method itself
- `assets/devices/`: pre-commit, CI, and lint configs you can copy in directly

---

## The hazard detector

Run it from wherever the plugin or the vendored skills live. Python 3.9+, standard library
only: no dependencies, so no dependency supply chain. `git` is needed for `--diff`,
`--staged` and `--since`; without it use `--paths`.

```bash
python3 plugins/poka-yoke/scripts/cli.py detect --diff        # uncommitted changes
python3 plugins/poka-yoke/scripts/cli.py detect --paths src/  # specific paths
python3 plugins/poka-yoke/scripts/cli.py registry --check     # CI: fail if the registry is stale
```

The tools also run directly, `scripts/detect_hazards.py` and `scripts/device_registry.py`, which is the convenient form in a pre-commit hook.

Skills reference the detector by a path **relative to the SKILL.md that names it**
(`../../scripts/detect_hazards.py`). That resolves anywhere the skills and scripts are
vendored together, which is why every install above copies `references/`, `scripts/` and
`assets/` alongside the skills rather than the skills alone.

> **Not published to a package registry.** A published command would resolve identically on
> every runtime without any path at all. Both PyPI and npm refuse a new name whose
> punctuation-stripped form matches an existing project, and `pokayoke` is taken on both, > registered on PyPI with no releases, published on npm. This is revisitable; see
> [RELEASING.md](../RELEASING.md).

## How the platform support is kept honest

Nine manifests maintained by hand is nine chances to update eight of them, and the failure
is silent: every file stays individually valid while disagreeing with the others. That is
not hypothetical here: a marketplace rename once left the README, the manifest and the
published repo pointing at three different names, and schema validation passed the whole
time because each file was fine on its own.

So the platform surface is generated and checked rather than remembered:

| Device | What it blocks |
|---|---|
| `scripts/sync_platform_manifests.py --check` | any of the 21 derived files drifting from `plugin.json` |
| `tests/test_portability.py` | a runtime-specific path variable, a script path that is absolute or does not resolve, a dispatcher that only works when installed, a manifest naming a skills directory that does not exist, a cross-document link pointing at a heading that no longer exists |
| CI `install` job | the documented install command not working |

`AGENTS.md` is a symlink to `CLAUDE.md`, and the other seven context files are one-line
pointers, for the same reason: a second full copy is how two sources of truth start
disagreeing.

## What still does not port

Automatic skill discovery. Claude Code selects a skill from its description; most other
runtimes rely on a context file being read and followed, which, as this project argues at
length, is rung zero. Where a runtime offers a real device (Cursor rules with globs, a
pre-commit hook, a CI gate), prefer that over a written instruction.
