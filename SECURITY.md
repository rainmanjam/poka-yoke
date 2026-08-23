# Security

## Reporting a vulnerability

Report privately via [GitHub Security Advisories](https://github.com/rainmanjam/poka-yoke/security/advisories/new).

That link only works once the repository is public. While it is private the advisory form
returns 404 for anyone outside the repository, so until then report by email to
rainmanjam@gmail.com with `poka-yoke security` in the subject.
Please do not open a public issue for anything exploitable.

Include what an attacker could do, the steps to reproduce it, and the version or commit. A
first response should come within a week.

## What this plugin does on your machine

Worth reading before installing, because this repository ships code that runs on your
machine and, in one case, code that runs on every tool call.

**The skills themselves are inert.** `SKILL.md` files and everything under `references/` are
Markdown. They are read into context and instruct the model. They execute nothing.

**Three scripts run only when you run them:**

| Script | What it does | Network | Writes |
|---|---|---|---|
| `scripts/cli.py` | Dispatches to the two below; runs nothing else | none | none |
| `scripts/detect_hazards.py` | Reads source files and reports pattern matches | none | none |
| `scripts/device_registry.py` | Reads source files, generates an index | none | only the path you pass to `--write` |

All three are Python standard library only. No dependencies, so no dependency supply chain.

**The templates in `assets/devices/` are the part to read before using.** They are examples
for you to adapt, not something the plugin installs. Two execute code:

- `claude-hooks/guard_dangerous_commands.py` is a `PreToolUse` hook. If you wire it up, it runs
  on **every tool call**, reads the tool input, and can deny the call. It makes no network
  requests and writes nothing. It fails open by design: on malformed input it exits 0 rather
  than blocking all tool use.
- `claude-hooks/suggest_poka_yoke.py` is a `UserPromptSubmit` hook. If wired up, it reads each
  prompt and may print a line of text. No network, no writes.

Read both before installing them. That is true of any hook from any source. A hook is
arbitrary code with your permissions on every tool call, and "it came from a plugin that talks
about safety" is not a security property.

**The benchmark harness (`benchmarks/run.py`) invokes the `claude`, `codex` and `agy` CLIs**
and therefore sends prompts to Anthropic, OpenAI and Google under whichever accounts those
CLIs are signed in to, against your quota on each. It is not run on install. It has a
`--max-calls` ceiling and a `--dry-run` that reports the planned call count before spending
anything.

## What it does not do

- No telemetry, analytics, or phone-home. Nothing in this repository reports usage anywhere.
- No network requests from the plugin's own scripts.
- No credentials read or stored. The example hook actively **denies** `Read`, `Edit`, `Write`
  and `NotebookEdit` calls against `.env`, `~/.aws/credentials`, SSH private keys, `.npmrc`,
  and `.pypirc`, because an agent that reads a secret can echo it into a log or a commit. It
  does not sandbox the shell, so `cat .env` in a `Bash` call is not covered by it.
- No automatic installation of hooks or config. Every device is a template you choose to apply.

## If you adapt the templates

The hook templates deny by pattern matching. Pattern matching on shell commands is
best-effort, and it is straightforward to construct a command that evades a regex: variable
indirection, quoting, `eval`, base64. Treat these hooks as a device against **mistakes**,
which is what they were written for, and not as a sandbox against a determined attacker.

For real isolation, restrict what the agent can reach rather than what it can type:
`permissions.deny` rules, a container, scoped credentials, and a database user without DDL
rights. This is the plugin's own argument applied to itself. A check that can be talked
around is a Warning, and Control means the action is unavailable.

Verify any hook you install actually fires. `tests/test_detector.py` shows the pattern: run
the blocked action, confirm the denial and its message, then run the legitimate neighbouring
action and confirm it still works. An untested hook fails open surprisingly often, and a hook
that silently does nothing is worse than no hook, because it creates confidence without
protection.

## Supported versions

Pre-1.0. Fixes land on `main`; there are no backported patch branches yet.
