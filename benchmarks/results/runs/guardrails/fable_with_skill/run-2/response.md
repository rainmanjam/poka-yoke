Using the poka-yoke **guardrails** skill for this — it's exactly the "we agreed to X and people still don't" case.

The short answer: nothing you can *say* will fix this, because the problem isn't the people — it's where the rule lives. CONTRIBUTING.md, a Slack pin, and two standup mentions are all the same device: someone's memory. In poka-yoke terms that's rung zero. A written rule has a half-life of about one onboarding, and 50% compliance after two weeks is the normal decay curve, not a discipline failure. The fix is to move the rule out of people's heads and into a gate that applies itself.

Concretely, in order of leverage:

1. **Make CI the enforcement, and make it required.** Add two checks to your pipeline — a format check (`prettier --check`, `black --check`, `gofmt -l`, whatever your stack uses) and the type checker (`tsc --noEmit`, `mypy --strict`, etc.) — then mark both as **required checks in branch protection**. This is the whole trick. Without branch protection, CI is advisory and you're back to asking nicely. With it, an unformatted or untyped PR physically cannot merge, and you never have to mention it in standup again.

2. **Make the formatter automatic, not a demand.** Formatting is the rare rule you can push all the way to "impossible to get wrong": commit editor settings that format on save (e.g. `.vscode/settings.json`), and add a pre-commit hook that *runs the formatter* rather than complaining about it. People don't have to remember anything; the file is just always formatted. Keep the CI check anyway — pre-commit hooks are bypassable with `--no-verify`, so the hook provides speed and CI provides authority. Run the same script in both so they can't drift.

3. **Baseline the type rule, then ratchet.** This is the part that decides whether the gate survives. If `mypy --strict` fails on 400 pre-existing untyped functions, the check gets reverted by Friday and teaches everyone that gates are noise. Enforce on changed files only, or generate a baseline and fail only on *new* violations, so the count can only go down. Existing code is grandfathered; new code meets the agreement automatically.

4. **Make the failure message teach.** When the gate fires, it should say the exact command that fixes it (`run: npx prettier --write .`), not "check failed." That's the one moment prose actually works — someone is guaranteed to be reading.

5. **Prove the gate fires before you trust it.** Open a deliberately unformatted, untyped PR, watch both checks go red with the message you wrote, fix it, watch them go green. An unverified guardrail is worse than none — it's confidence without protection.

One thing to leave alone: don't add a review checklist item or a PR template checkbox for this. That's the same rung-zero device with extra ceremony.

If you tell me the language/stack and CI system (GitHub Actions?), I can write the actual workflow, the pre-commit config, and the exact branch-protection settings to click — the repo I'm sitting in has ready-made templates for precisely this.