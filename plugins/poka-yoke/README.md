# poka-yoke

Mistake-proofing for software: a dependency-free hazard scanner, installable pre-commit and CI
devices, and 11 skills that apply the same method while you design. Shigeo Shingo's method
applied to code, process, interfaces, infrastructure, and AI.

The scanner is the part that does not decay, because it is not in the model's context at all.
The skills are instructions, and instructions degrade as a session fills; invoke a mode early
and fresh for a design decision rather than assuming it still shapes behaviour hours in.

See the [repository README](../../README.md) for the method, installation, and rationale, and
[docs/install.md](../../docs/install.md) for the 19 supported runtimes and their tiers.

## Layout

```
skills/
├── poka-yoke/            router + doctrine (start here)
├── audit/                find footguns in code that already exists
├── design/               make misuse unexpressible in new interfaces
├── guardrails/           pre-commit, CI, lint, DB constraints, branch protection
├── retro/                incident → device that kills the whole class
├── ux/                   forms, destructive actions, flows users get wrong
├── ops/                  deploys, migrations, rollback, blast radius
├── data/                 pipelines, warehouses, dbt models, metrics
├── authz/                tenant isolation, IDOR, row-level security
├── llm/                  AI features you ship to users
└── agent-guardrails/     AI agents working on your repo

references/               loaded on demand, never into every session
├── hazard-catalog.md     28 hazard shapes by lens, each with its device
├── ux-patterns.md        interface devices sized by consequence
├── lang-typescript.md
├── lang-python.md
└── lang-rust-go.md

scripts/                  the executable devices, standard library only
├── cli.py                one entry point: `detect` and `registry`
├── detect_hazards.py     42 pattern rules over 18 shapes; a Python AST pass adds 2 more
└── device_registry.py    generates the device registry by reading the code

assets/devices/           templates you choose to apply; read before installing
├── claude-hooks/         PreToolUse guard, UserPromptSubmit suggester
├── github-actions/       CI gates including migration safety
├── pre-commit/           .pre-commit-config.yaml
└── lint/                 mistake-prevention rule sets for four languages

.claude-plugin/           the source of truth, the one manifest you edit by hand

.codex-plugin/   .cursor-plugin/ .devin-plugin/  .grok-plugin/
.hermes-plugin/  .kimi-plugin/   .kiro/          .qoder-plugin/
                          per-runtime manifests, every one generated from
                          .claude-plugin/plugin.json (never edit by hand)
```

## Editing

The router's dispatch table in `skills/poka-yoke/SKILL.md` is what makes the other skills
discoverable. Update it when adding or renaming a mode.

Name, version, description and keywords live in `.claude-plugin/plugin.json` and nowhere else.
`../../scripts/sync_platform_manifests.py` derives the eight sibling manifests from it, plus
`gemini-extension.json`, `.agents/plugins/marketplace.json` and `commands/*.toml` at the
repository root. Edit the source, re-run the script, commit what it writes; `--check` fails CI
when a derived copy has drifted.

**Cross-file references are relative to the `SKILL.md` that names them**
(`../../references/hazard-catalog.md`, `../../scripts/detect_hazards.py`). Do not use
`${CLAUDE_PLUGIN_ROOT}`: it resolves on Claude Code and silently resolves to nothing on the
other eighteen, where the skill then points at a file it cannot read.
`tests/test_portability.py` enforces this.

Skill descriptions compete for a truncated listing budget. Put concrete domain nouns and
quoted user phrasing in the first ~160 characters, or the trigger words are what gets cut.
`tests/test_skill_listing.py` enforces the budget.

## Validate before committing

```bash
claude plugin validate . --strict
python3 ../../tests/test_detector.py
python3 ../../tests/test_portability.py
python3 ../../tests/test_skill_listing.py
python3 ../../scripts/sync_platform_manifests.py --check
```

Or run the devices directly:

```bash
python3 scripts/cli.py detect --diff
python3 scripts/cli.py registry --check
```
