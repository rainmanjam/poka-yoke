## Goal Description
The core philosophy of this repository states: **"If your change relies on someone remembering something, it is not finished. A comment, a checklist item, a line in this file — those are training. Training degrades."** 

Relying on instructions in `CONTRIBUTING.md`, Slack pins, and standup reminders is a form of training, which explains why PRs are still coming in unformatted and untyped. To solve this, we need to introduce a "device"—an automated check that catches the problem before it merges.

This plan proposes adding automated formatting (using `ruff`) and type checking (using `mypy`) as a CI check and a pre-commit hook.

> [!NOTE]  
> "When you fix something here, ask what device would have caught it, and add that too. Every check under `.github/workflows/validate.yml` exists because something drifted silently first." — `AGENTS.md`

## User Review Required
> [!IMPORTANT]
> - **Tooling Choice:** We propose using `ruff` for both formatting and linting (it's extremely fast and replaces Black/Flake8), and `mypy` for static type checking. Let me know if you prefer different tools.
> - **Strictness:** Adding a type checking CI job means that un-typed or poorly-typed PRs will fail the build and be blocked from merging.

## Open Questions
> [!WARNING]
> The team agreed to add type annotations to **new** code. However, running `mypy` in CI will check existing code as well. 
> Should we:
> 1. Type-annotate all 23 existing Python files so the whole codebase passes `mypy --strict`?
> 2. Or configure `mypy` to be permissive on existing code and only complain about glaring errors, while enforcing stricter rules incrementally?

## Proposed Changes

### Configuration
We will add standard configuration files to define the formatting and typing rules.
#### [NEW] pyproject.toml
```toml
[tool.ruff]
line-length = 100
target-version = "py39"

[tool.ruff.lint]
select = ["E", "F", "I"] # PEP8, Pyflakes, Isort

[tool.mypy]
python_version = "3.9"
check_untyped_defs = true
disallow_untyped_defs = false # (Adjustable based on open question)
```
#### [NEW] .pre-commit-config.yaml
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.3.4
    hooks:
      - id: ruff
        args: [ --fix ]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.9.0
    hooks:
      - id: mypy
        additional_dependencies: [types-requests]
```

---

### CI Pipeline
#### [MODIFY] .github/workflows/validate.yml
We will add a new job to fail the build if code is unformatted or untyped.
```yaml
  formatting-and-typing:
    name: formatting and typing
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install tools
        run: python3 -m pip install ruff mypy
      - name: Check formatting and linting
        run: |
          ruff format --check .
          ruff check .
      - name: Check typing
        run: mypy .
```

---

### Code Remediation
#### [MODIFY] All Python files (*.py)
We will run `ruff format .` to format the existing codebase. We will also resolve any existing type errors that block the CI check from passing.

## Verification Plan

### Automated Tests
1. Break the formatting deliberately in a file, run `ruff format --check .`, and verify it fails.
2. Introduce a type mismatch deliberately, run `mypy .`, and verify it fails.
3. Push to a test branch to verify the `.github/workflows/validate.yml` job catches both errors in CI.

### Manual Verification
You can run `pre-commit install` and try to make an unformatted commit, ensuring the pre-commit hook automatically fixes it or blocks it.