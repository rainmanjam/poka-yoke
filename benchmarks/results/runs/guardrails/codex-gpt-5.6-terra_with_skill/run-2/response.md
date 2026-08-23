You’ve already done the things that rely on memory. The next move is to make the repo reject violations.

- Run formatting automatically on changed files in a pre-commit hook for immediate feedback.
- Run the same formatter and type checker as required CI checks; protect the main branch so failing checks cannot merge. This is the actual enforcement.
- Keep hooks fast; people bypass slow hooks. CI can run the full repository check.
- If existing code has many type issues, baseline it and fail only on new or changed violations. Ratchet the baseline down over time rather than creating a wall of failures.
- Make failures actionable: e.g., “Formatting required — run `npm run format`” and “New code must pass `mypy`/`tsc`; add annotations or narrow the changed-file scope.”

In poka-yoke terms: Slack, standups, and `CONTRIBUTING.md` are rung 0 (training). A required CI check with branch protection is a warning device that prevents an unformatted or untyped PR from becoming a merged defect. Full control would mean formatter-on-save plus generated/typed interfaces where possible, but CI remains the non-bypassable backstop.

Before calling it done, prove the guardrail: deliberately submit an unformatted, untyped change, confirm both local and CI checks fail, then fix it and confirm they pass.