Stop adding reminders; make the repository enforce the agreement.

- Add CI checks that fail PRs with formatting drift or missing required type coverage.
- Provide a pre-commit hook that runs the formatter and relevant type checker automatically.
- Make the formatter auto-fix on save or pre-commit so compliance is nearly effortless.
- Protect the main branch so required checks cannot be bypassed.
- Define the rule precisely: which formatter, which type checker, and what “new code must be typed” means.

Then prove each guard works: intentionally submit unformatted and untyped changes, confirm the hook/CI blocks them, and restore the code. The issue isn’t that people failed to hear the policy—it’s that the workflow still permits the undesired outcome.