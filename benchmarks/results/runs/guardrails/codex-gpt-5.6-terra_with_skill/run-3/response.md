Stop adding reminders; turn the agreement into a merge gate.

- Run the formatter automatically in editors/pre-commit for fast feedback, but also make “format check” a required CI check with branch protection. Hooks alone are bypassable.
- Make type checking required in CI too. To enforce “new code is annotated,” add a lint/type rule scoped to changed files or generate a baseline and fail only on new violations. This avoids punishing the team for legacy debt.
- Keep commit-time checks under ~5 seconds; run broader checking in CI.
- Make failures actionable: name the file/rule and give the exact fix command.
- Prove each guardrail works: deliberately submit unformatted and untyped code, verify the PR cannot merge, then fix it and verify it passes.

The mistake is not that engineers forgot; the workflow currently lets incomplete work pass. A protected required check is the control: unformatted or newly untyped changes may be authored, but cannot become merged code.