## Goal Description

**Defect:** Half the PRs are unformatted and untyped.
**Mistake:** Engineers are committing and opening PRs without running the formatter or adding type annotations.
**Hazard:** The repository relies on human memory and voluntary compliance (Training/Documentation, which is Rung 0 in the Poka-Yoke framework). There are no system constraints to block unformatted or untyped code from being committed or merged.

The goal is to move from **Rung 0 (Training)** to **Rung 1/2 (Control/Warning)**. We will achieve this by setting up a `pre-commit` hook for fast, early feedback, and a GitHub Actions CI workflow to act as the authoritative gate that blocks merges.

## User Review Required

> [!IMPORTANT]
> To make this enforcement strictly binding, you must configure **Branch Protection** on the `main` branch in GitHub:
> 1. Go to **Settings > Branches** in your repository.
> 2. Check **Require status checks to pass before merging**.
> 3. Add the `type-check` and `format-check` jobs to the required list.
> 
> Without this step, the CI workflow is merely advisory (Rung 2).

> [!WARNING]
> Turning on strict formatting and type checking for the entire codebase at once might cause hundreds of errors. The proposed plan ratchets these checks: `pre-commit` is set to run only on changed files by default, but we will configure the CI workflow to strictly check the whole codebase (or just changed files if you prefer). Please confirm if you want the CI to fail on *existing* untyped code, or if we should scope `mypy` to only check newly modified files.

## Open Questions

1. For type checking, the plan proposes using `mypy`. Is `mypy` acceptable, or do you use another type checker (like `pyright`)?
2. For formatting, the plan proposes using `ruff`. Are you currently using `ruff`, `black`, or something else for formatting?
3. Do you want to enforce these checks only on changed files in CI to avoid blocking current work on legacy code (the "baseline and ratchet" approach), or enforce it globally?

## Proposed Changes

---
### Pre-Commit Hooks
We will introduce a `.pre-commit-config.yaml` at the root of the repository to provide fast feedback (seconds) before a commit is finalized.

#### [NEW] .pre-commit-config.yaml
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.14.5
    hooks:
      - id: ruff-check
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.11.2
    hooks:
      - id: mypy
        additional_dependencies: [types-all]
        pass_filenames: true
```

---
### GitHub Actions CI Gates
Since `pre-commit` can be bypassed with `--no-verify`, we will add a required CI workflow to enforce formatting and typing. This will serve as the un-bypassable gate.

#### [NEW] .github/workflows/poka-yoke-gates.yml
```yaml
name: poka-yoke-gates

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  format-check:
    name: format check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install Ruff
        run: python3 -m pip install ruff
      - name: Check Formatting
        run: ruff format --check .
      - name: Check Linting
        run: ruff check .

  type-check:
    name: type check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install Mypy
        run: python3 -m pip install mypy
      - name: Run Mypy
        run: mypy --strict plugins/ scripts/ tests/
```

## Verification Plan

### Automated Tests
1. Commit a file with bad formatting and no types.
2. Verify that `pre-commit run --all-files` catches the errors and blocks the commit.
3. Push the branch and verify that the `poka-yoke-gates.yml` workflow fails in GitHub Actions.
4. Fix the formatting and types, push again, and verify the workflow passes.

### Manual Verification
1. Open the GitHub repository settings and ensure the branch protection rules are applied.
2. Verify that a PR cannot be merged if the `format-check` or `type-check` jobs fail.