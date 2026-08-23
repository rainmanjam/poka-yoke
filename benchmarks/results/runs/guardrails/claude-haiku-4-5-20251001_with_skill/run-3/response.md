Now I'll propose the specific devices for your situation. Here's what needs to happen:

## The Device: Formatting + Type Checking Gates

**What will prevent the mistake:**
- **Pre-commit hook** runs Prettier on changed files in 1-2 seconds (fast feedback, bypassable with `--no-verify`)
- **Required CI check** runs the same checks on every PR (enforcement, cannot be bypassed with branch protection)
- **Type check in CI** ensures `tsc --noEmit` passes (makes the type annotation design-time device load-bearing)

This reaches **Rung 2 (Warning)** — the mistake is possible but announced at the moment it happens. Control (Rung 1) would require the formatter to run automatically on stage, which you could add later with `git commit --amend` hooks, but Warning is the standard starting point.

**What it makes impossible:**
- Unformatted code reaching main (the hook catches it locally, CI blocks it if the hook is bypassed)
- Untyped code that should be typed (type checker fails the PR)
- The need to rely on "everyone remember to run the formatter" (it's now a device)

**What it leaves possible (intentionally):**
- Pre-existing unformatted code won't block your team — only *new* violations are caught. The violation count ratchets down over time, never up.
- Someone with `--no-verify` can still bypass the pre-commit hook, but CI will catch them.

---

I need to see your current `.github/workflows` and `package.json` to show you the exact config. Quick check:

```bash
ls -la .github/workflows/ 2>/dev/null | head -10
grep -E '"prettier"|"typescript"|"tsc"' package.json 2>/dev/null
```

That will tell me if Prettier and TypeScript are already installed, so I can show you the complete config to add. Should I run those?