Using the poka-yoke skill (routed to `guardrails`, since this is exactly its trigger case: "we agreed to X and people still do not").

**Why it's stuck**: CONTRIBUTING.md, Slack pins, and standup mentions are all the same device — a human has to remember and choose to comply. In the mistake-proofing ladder that's rung 0 ("not a poka-yoke," it's training), and training has a documented half-life of about one onboarding cycle. No amount of repeating it moves the rung. You need the rule to be enforced by something that runs automatically, not recalled.

**The fix is to pick the earliest gate that can hold each rule, backed by one that can't be skipped**:

| Gate | Speed | Bypassable? | Use for |
|---|---|---|---|
| Pre-commit hook | seconds | yes (`--no-verify`) | auto-run the formatter, fail fast on missing types |
| CI required check | minutes | no, with branch protection | re-run the same checks — this is the actual enforcement |

Two things matter more than the tooling choice:

1. **Never rely on the pre-commit hook alone.** People under deadline pressure use `--no-verify`. The hook is for speed/local feedback; the CI check + branch protection is what actually blocks a merge.
2. **Baseline first, then ratchet.** If you turn strict type-checking on across the whole repo today, you'll get hundreds of pre-existing failures, the team will feel punished for old code, and the rule gets reverted by Friday. Instead: enforce the formatter/types only on *changed lines* (or a baseline of existing violations that can only shrink), so new PRs are held to the standard without retroactively blocking everyone.

Also make the failure message teach — "line 42: missing type annotation, run `mypy path/file.py` to check locally" gets fixed; a bare `error: rule violated` gets bypassed or ignored.

To get you the actual config (`.pre-commit-config.yaml` + a GitHub Actions required check), I need your stack: is this Python (`black`/`ruff format` + `mypy`) or TypeScript (`prettier` + `tsc --noEmit`), and are you on GitHub with branch protection available? Once I know that I can write the working config rather than a generic template — that's the piece that will actually move you off 50%.