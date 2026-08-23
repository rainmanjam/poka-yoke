You're not doing anything wrong with the *wording*. You're using the wrong class of control — and you already know this, because you wrote the fix and never installed it.

## The diagnosis

A CLAUDE.md rule is a **warning label**. In your own hazard catalog's terms it's detection-level: it depends on the agent reading the label, holding it in attention across a long context, and choosing compliance every single time. Warning labels get ~90% compliance from humans and from models. Caps and repetition don't change the control class — they just spend tokens buying a little more salience within the same weak tier. That's why you got "one time in ten" rather than "never": you're at the natural ceiling for that tier.

The nine-in-ten successes are also misleading you. They make the rule *look* like it works, so the instinct is to strengthen the label rather than replace it.

## What actually closes it

`plugins/poka-yoke/assets/devices/claude-hooks/guard_dangerous_commands.py:31` already denies force-push — including the `--force-with-lease` carve-out you got right. A `PreToolUse` deny is a **control**: the action is refused at the harness layer, so model compliance stops being a variable. Compliance goes from ~90% to 100% and stays there regardless of context length or how buried the rule is.

So: force-push is solved the moment you wire that hook into `.claude/settings.json`. `src/generated/` isn't covered yet — it needs a path rule alongside `PROTECTED_PATHS`.

`★ Insight ─────────────────────────────────────`
- The deny *reason* is load-bearing. A bare refusal makes the agent invent a workaround — `cat > file` instead of Write. Your file's docstring says this; the `src/generated/` rule needs a reason that names the source of truth.
- Warnings degrade with context length; controls don't. That asymmetry is the whole argument for hooks over CLAUDE.md.
`─────────────────────────────────────────────────`

## The decision I need from you

`src/generated/` has a legitimate write path — regeneration. A blanket path deny blocks the codegen run too, and a hook people disable is worth less than the label.

**In `guard_dangerous_commands.py`, how should the escape hatch work?** Roughly 5–10 lines. The options trade off differently:

- **Deny Edit/Write only, allow Bash** — codegen runs as a subprocess and passes through. Simple; leaky if the agent shells out to `sed`.
- **Deny all writes, no hatch** — you run codegen yourself. Strongest, most friction.
- **Deny unless the command matches your generator invocation** — precise, but the allowlist rots when the build changes.

Which fits how your generated code actually gets rebuilt?