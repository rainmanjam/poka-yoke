## Goal Description
The core problem is that you are relying on **training** (Slack, standup, `CONTRIBUTING.md`), and as this repository's own `AGENTS.md` explicitly states: **"Training degrades. If your change relies on someone remembering something, it is not finished."** 

People will always forget instructions. To solve this permanently, we need to replace the training with **devices**—automated systems that enforce the rules so that it becomes impossible (or at least very difficult) to commit or merge unformatted or untyped code.

We will add two devices:
1. **A local device (pre-commit hook):** Formats code and checks types on the developer's machine *before* the commit succeeds.
2. **A systemic device (CI/CD pipeline):** Blocks pull requests from merging if they violate formatting or typing rules, providing an unbypassable gate.

## User Review Required
> [!IMPORTANT]
> The plan proposes setting up `ruff` for formatting and `mypy` for typing since this is a Python project, but these can be swapped for other languages (e.g., `prettier` and `tsc` for TypeScript). Please confirm the exact language and tools you want to enforce.

## Open Questions
> [!WARNING]
> 1. Should we apply this directly to the current repository (`poka-yoke`), or are you asking for advice for another project? (If it's for this repository, I will create the files outlined below).
> 2. For typing, how strict do you want to start? We can start with a baseline check or enforce `--strict` mode immediately.

## Proposed Changes

### Configuration Device
Add a pre-commit configuration to format code and run type checks before a commit can be created.

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
        additional_dependencies: [types-requests] # Add relevant type stubs here
```

### Continuous Integration Device (The Gate)
Add a workflow check that guarantees no unformatted or untyped code can reach the `main` branch.

#### [NEW] .github/workflows/lint-and-type.yml
```yaml
name: code quality

on:
  pull_request:
  push:
    branches: [main]

jobs:
  format-and-type:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          
      - name: Install dependencies
        run: pip install ruff mypy
        
      - name: Check Formatting (ruff)
        run: ruff format --check .
        
      - name: Type Check (mypy)
        run: mypy .
```

## Verification Plan
1. **Automated Tests**: I will deliberately create an unformatted, untyped Python file and verify that the pre-commit hook catches it and fails.
2. **Manual Verification**: You will be able to review the GitHub Actions workflow and confirm it triggers correctly on PRs.