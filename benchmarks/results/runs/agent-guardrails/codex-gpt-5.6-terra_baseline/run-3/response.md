You’re using prose to enforce things that need to be enforced by tooling. Capitals and repetition may make the rule more visible, but they don’t create a boundary—and can crowd out more useful context.

Keep `CLAUDE.md` short and operational, but move the guarantees elsewhere:

```json
// .claude/settings.json
{
  "permissions": {
    "deny": [
      "Edit(/src/generated/**)",
      "Bash(git push *--force*)",
      "Bash(git push *-f*)"
    ],
    "disableBypassPermissionsMode": "disable"
  },
  "sandbox": {
    "enabled": true,
    "failIfUnavailable": true,
    "allowUnsandboxedCommands": false,
    "filesystem": {
      "denyWrite": ["./src/generated"]
    }
  }
}
```

The `Edit` rule blocks Claude’s native editor; sandbox write-denial covers subprocesses too. Claude’s docs specifically note that file-tool deny rules alone do not reliably constrain arbitrary Bash programs. [Claude Code permissions](https://code.claude.com/docs/en/permissions)

For force-push, treat local protections as a helpful tripwire, not the final safeguard. Enforce “no force pushes” in your Git host’s protected-branch rules. A local hook or Claude permission can be bypassed with another client or `--no-verify`; the remote is the actual device.

Also add CI checks that fail a PR if `src/generated/` changes. If generated output sometimes legitimately changes, instead require CI to regenerate it and fail unless the committed result exactly matches—this distinguishes a valid generator run from hand edits.

A better `CLAUDE.md` line would be:

> `src/generated/**` is protected. Do not modify it. If the requested change requires regenerated output, explain the required generator command and wait for approval.

That line guides Claude. Permissions, sandboxing, CI, and protected branches make it unable—or unable to merge the result—when it ignores the guidance.