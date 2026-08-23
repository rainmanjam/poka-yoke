## Goal Description
You are encountering a common failure mode: Claude occasionally ignores strict text instructions placed in `CLAUDE.md` (e.g., "never edit files in src/generated/", "never force push"). 

As outlined in this repository's `CLAUDE.md` and `AGENTS.md`, the core philosophy here is: **"If your change relies on someone remembering something, it is not finished."** 

Instructions in a markdown file—even capitalized and repeated—are a form of "training," and training degrades. LLMs (just like humans) will probabilistically miss or ignore them. The solution is to replace these textual instructions with **devices** (poka-yokes) that physically prevent the mistakes from occurring.

## User Review Required
> [!IMPORTANT]
> The plan below shifts the responsibility of compliance from the agent (reading `CLAUDE.md`) to the system (CI/CD and Git configurations). Please review the proposed devices to ensure they fit your project's workflow.

## Proposed Changes

We will implement physical constraints (devices) to enforce your rules, rendering the `CLAUDE.md` instructions unnecessary.

### 1. Device for: "never force push"
You cannot reliably prevent force pushes via text instructions. This must be a repository setting:
1. Navigate to **Settings > Branches** in your GitHub repository.
2. Edit or add a branch protection rule for `main` (and any other critical branches).
3. Ensure **"Allow force pushes"** is **disabled**.
*Now, even if Claude (or a human) attempts a force push, the git server will outright reject the command.*

### 2. Device for: "never edit files in src/generated/"
We will add two layers of defense to block manual edits to generated files.

#### [NEW] Local Pre-commit Hook
We can add a pre-commit hook that immediately rejects local commits if they touch the generated directory. If you use `pre-commit`, add this to your `.pre-commit-config.yaml`:
```yaml
repos:
  - repo: local
    hooks:
      - id: forbid-generated-edits
        name: forbid manual edits to src/generated/
        entry: Manual edits to src/generated/ are strictly forbidden.
        language: fail
        files: ^src/generated/
```

#### [NEW] CI Pipeline Check
To guarantee these files aren't modified in pull requests, we can add a check to your GitHub Actions workflows (e.g., inside `.github/workflows/validate.yml`):
```yaml
  generated-files:
    name: check generated files
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Ensure src/generated/ is not manually edited
        run: |
          if git diff --name-only origin/main | grep -q "^src/generated/"; then
            echo "::error::Manual edits to src/generated/ are forbidden. Please update the source generator instead."
            exit 1
          fi
```

## Verification Plan

### Automated Tests
1. **CI Verification**: Open a pull request that modifies a file in `src/generated/`. The GitHub Actions workflow will fail loudly, blocking the PR from being merged.
2. **Pre-commit Verification**: Run `pre-commit run --files src/generated/example.ts`. The hook will trigger and block the commit.

### Manual Verification
1. Attempt to run `git push --force origin main`. GitHub will reject the push with an error stating that force pushes are not allowed on this branch.