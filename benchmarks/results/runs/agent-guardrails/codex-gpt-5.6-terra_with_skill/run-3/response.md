You’re treating a reliability problem as a wording problem. Caps and repetition are still instructions—training, not enforcement. Claude can miss or override them under context pressure, ambiguity, or tool-command variations.

Replace both rules with controls in committed `.claude/settings.json`:

```jsonc
{
  "permissions": {
    "deny": [
      "Bash(git push --force:*)",
      "Bash(git push -f:*)",
      "Edit(./src/generated/**)",
      "Write(./src/generated/**)"
    ]
  }
}
```

Add a `PreToolUse` hook too. Deny patterns are string-prefix matches, so they can miss `git push origin main --force`, chained commands, and flag variants. The hook should inspect every Bash command and deny any force-push; it should also deny writes whose resolved target is under `src/generated/`.

Its denial should redirect rather than merely say “no,” e.g.:

> Blocked: force-push rewrites shared remote history. Create a new commit and push normally; if rewriting is genuinely required, ask the user to perform it.

For generated files:

> Blocked: `src/generated/` is produced by its generator. Change the source/schema and run the documented generation command; do not edit generated output.

Also put a generated-file header in those files, such as `// Code generated … DO NOT EDIT.` That’s a useful local signal, but the hook/path deny is the actual control.

Finally, prove both controls work: attempt a force push and a direct generated-file edit; confirm they are denied with those messages. Then verify ordinary `git push` and editing the generator input still work. An untested guardrail is just another instruction wearing a JSON hat.