In your retro, the team created a **Rung 0 (Training)** device. A line in `CONTRIBUTING.md`, a Slack pin, and a verbal reminder all rely on human memory. As the `poka-yoke` methodology highlights, training degrades—usually with a half-life of about one onboarding. It's completely expected that two weeks later, people are forgetting. 

To solve this, we need to stop trying to make the team remember, and start making the mistake either impossible to merge or immediately visible when they make it. We need to introduce mechanical guardrails:

1. **A CI Gate (Rung 1: Control):** This is the ultimate enforcement. We wire the formatter and type checker into a GitHub Actions workflow and require it to pass before merging. Unformatted or untyped code physically cannot be merged.
2. **A Pre-commit Hook (Rung 2: Warning):** CI takes minutes and breaks flow. We add a local pre-commit hook so developers get feedback in seconds. We *never* rely on this alone since people can bypass it with `--no-verify` when in a hurry, but it serves as a fast early warning.
3. **The Ratchet Strategy:** Since half the PRs are failing right now, turning on strict enforcement globally will cause hundreds of failures and the rule will get reverted by Friday. We must enforce this on **changed files only** so existing violations don't block anyone, and the count only goes down.

I have created a detailed implementation plan in the artifact above. 

To give you the exact, working configuration for your repository as the guardrails skill recommends, **what language and stack are you using** (e.g., Python with Ruff/Mypy, TypeScript with Prettier/TSC, etc.)? Once you let me know, we can proceed with setting up the gates!
{"answer":"I have read the router skill, routed to the `guardrails` skill, read it and its referenced assets, and formulated a response and implementation plan based strictly on the poka-yoke methodology. I created an artifact for the user to review the plan and requested their tech stack so we can build the concrete pre-commit and CI configuration files.","toolAction":"Finishing task","toolSummary":"Finish task"}