Two weeks of docs, a pin, and two standup mentions is three attempts at the same rung-0 device — and rung 0 (comments, wiki pages, verbal reminders) doesn't fail loudly enough to change behavior, no matter how many channels you push it through. That's why half the PRs are still slipping through: nothing in the actual merge path can say no.

**The fix isn't "communicate harder," it's moving the rule from a document into a gate.** Per the guardrails method, pick the earliest gate in the pipeline that can hold the rule and back it with one that can't be skipped:

| Gate | Speed | Bypassable? |
|---|---|---|
| Editor + lint (format-on-save, type errors inline) | instant | yes, but nobody notices they're bypassing |
| Pre-commit hook (formatter + basic type check) | seconds | yes (`--no-verify`) |
| CI required check | minutes | **no**, if branch protection requires it |

The pre-commit hook is for speed (catches it before the PR exists); the CI check is for authority (nothing merges without it, `--no-verify` can't touch it). Relying on the hook alone is the most common near-miss here — someone under deadline runs `--no-verify` once, it works, and it becomes habit.

**One landmine to avoid:** if you flip strict type-checking on across the whole repo right now, you'll likely get hundreds of pre-existing failures, the check will feel broken, and someone will get permission to disable it "temporarily." Baseline first — enforce formatting/types on **changed files only**, or snapshot current violations and fail only on *new* ones. The count only goes down from there, and nobody gets blocked on code they didn't touch.

To write you the actual config (pre-commit + CI workflow), I need your stack — what language/formatter (Prettier/Black/gofmt?) and CI provider (GitHub Actions?). This repo itself doesn't have a `package.json` or `pyproject.toml` at the root, so I'm guessing your team's codebase is elsewhere — confirm the path if it's in this monorepo somewhere.