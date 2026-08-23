I read the router and it points at **`guardrails`** — a rule that needs enforcing rather than documenting. Its description names your situation almost verbatim: *"we agreed to X and people still do not."*

## The diagnosis

You've tried four things: a retro agreement, CONTRIBUTING.md, a Slack pin, and two standup mentions. Those look like four interventions, but they're one device repeated four times — **rung 0 on the poka-yoke ladder: training.** Every one of them works only if a person remembers at the moment of committing.

50% compliance after two weeks isn't a discipline problem. It's the ordinary half-life of a remembered rule. And the harder truth is that your other 50% *are* paying a cost — the tax of remembering — that the first 50% aren't. That asymmetry is what makes "mention it again in standup" feel unfair to the people already complying.

Nothing in your pipeline can currently tell a formatted PR from an unformatted one. So the answer to "what else can I do to get people to follow it" is: **stop trying to get people to follow it.** Make one of the rules unnecessary and the other one unmergeable.

`★ Insight ─────────────────────────────────────`
Your two rules need *different* devices, and lumping them together is why one message can't fix both. Formatting is **deterministic and auto-applicable** — a machine can just do it, so it should never have been a rule at all. Type annotations require human judgment — no tool can write them for you, so this one genuinely needs a gate that refuses work.
`─────────────────────────────────────────────────`

I'm assuming Python (ruff + mypy), since "type annotations" is Python vocabulary. The TypeScript swap is two lines and I've noted it below.

---

## Rule 1: formatting — delete the rule, don't enforce it

Nobody should be *remembering* to run a formatter. Three layers, none of which involve a human:

**a. Format on save** (`.vscode/settings.json`, committed to the repo):
```json
{
  "editor.formatOnSave": true,
  "[python]": { "editor.defaultFormatter": "charliermarsh.ruff" }
}
```

**b. Auto-fix at commit** — `.pre-commit-config.yaml`. Note this hook *rewrites* the file rather than complaining about it:
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.5
    hooks:
      - id: ruff-format          # poka-yoke: formats the commit instead of asking someone to remember [control]
      - id: ruff-check
        args: [--fix, --exit-non-zero-on-fix]
```

**c. CI as the authority.** Pre-commit is bypassable by design — `git commit --no-verify` exists and people under deadline use it. The hook gives you speed; CI gives you enforcement. Same tool in both so they can't drift.

Before you turn this on: land **one** "format the world" commit, then add its SHA to `.git-blame-ignore-revs`. Otherwise the first formatted PR touches 400 files and everyone blames the device.

---

## Rule 2: type annotations — a required check, ratcheted

You cannot auto-apply this one, so it has to be a gate. The thing that kills gates like this is turning `mypy --strict` on across an existing codebase, getting 800 errors, and having the rule reverted by Friday. **Enforce on changed files only** — new code must be typed, existing code is grandfathered, and the violation count can only go down.

```yaml
# .github/workflows/checks.yml
name: checks
on: [pull_request]

jobs:
  format:
    name: format            # mark Required in branch protection
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: astral-sh/ruff-action@v3
        with: { args: "format --check" }

  types:
    # poka-yoke: blocks new untyped functions without demanding the whole repo be typed first
    name: types on new code
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
        with: { fetch-depth: 0 }
      - uses: actions/setup-python@v6
        with: { python-version: "3.12" }
      - run: pip install mypy
      - name: Type-check changed files only
        env:
          BASE_REF: ${{ github.base_ref || 'main' }}
        run: |
          mapfile -t CHANGED < <(git diff --name-only --diff-filter=d \
                                   "origin/${BASE_REF}"...HEAD -- '*.py')
          if [ ${#CHANGED[@]} -eq 0 ]; then echo "No Python changed."; exit 0; fi
          if ! mypy --disallow-untyped-defs --follow-imports=silent "${CHANGED[@]}"; then
            echo "::error::New or edited code needs type annotations."
            echo "Only the files you touched are checked — the rest of the repo is grandfathered."
            echo "Run locally: mypy --disallow-untyped-defs --follow-imports=silent <your files>"
            exit 1
          fi
```

That failure message is doing real work. A gate that says `error: rule violated` produces a confused engineer and a workaround; one that names the fix command produces a fixed PR.

**Honest limitation:** `--follow-imports=silent` means cross-module type errors slip through. It's the right trade for "new code must be annotated" — if you later want true strictness, add [`mypy-baseline`](https://pypi.org/project/mypy-baseline/) to snapshot existing errors and fail only on new ones. That's a stricter ratchet at the cost of one dependency.

**TypeScript swap:** `ruff-format` → `prettier --check`, and the types job → `npx tsc --noEmit` (whole-project, since tsc has no changed-files mode; use `noImplicitAny` and ratchet with `// @ts-expect-error` cleanup).

---

## The step that makes all of it real

Without branch protection, that workflow is advisory and the entire device is inert:

```bash
gh api -X PUT repos/OWNER/REPO/branches/main/protection \
  -f 'required_status_checks[strict]=true' \
  -f 'required_status_checks[contexts][]=format' \
  -f 'required_status_checks[contexts][]=types on new code' \
  -F 'enforce_admins=false' \
  -f 'required_pull_request_reviews[required_approving_review_count]=1' \
  -F 'restrictions=null'
```

## Then prove it fires

An untested guardrail is worse than none — it creates confidence without protection. Before you announce it: open a throwaway PR with a deliberately unformatted, unannotated function. Watch both checks go red. Read the error message as a teammate would. Fix it, watch them go green. Screenshot both and put *that* in Slack instead of a reminder.

## Finally, edit CONTRIBUTING.md

Not to strengthen the rule — to delete it. Replace the two bullets with a pointer to the device:

> Formatting and type checks run automatically (`pre-commit install` once; CI enforces on every PR). You don't need to remember either.

Leaving the prose in place quietly teaches the team that documentation is how rules get enforced here, which is the belief that produced the current 50%.

---

**One decision I'd rather you make than guess at:** the ratchet policy. Changed-files-only (above) is the gentlest landing and I'd default to it — but it means a new untyped function added to a legacy module gets caught, while a legacy function *edited* in place also gets caught, which occasionally forces someone to annotate code they only meant to fix a typo in. The alternatives are per-module opt-in (`[mypy-myapp.billing.*] disallow_untyped_defs = true`, zero surprise but slow to spread) or a full baseline file (strictest, one dependency). Which friction your team will actually tolerate is a call you can make and I can't.