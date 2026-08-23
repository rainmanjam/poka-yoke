Nothing's wrong with your wording. The mechanism is wrong.

**CAPS and repetition don't add enforcement.** A CLAUDE.md instruction is an influence on sampling, not a gate on execution. One-in-ten is roughly what a well-written soft rule looks like — better phrasing might get you to one-in-thirty, but never to zero, because there's no step in the loop where anything checks the rule before the tool call goes out. Saying it twice in caps mostly costs you salience elsewhere: when several lines are shouting, none of them are.

This is the ladder from your own plugin. You've written a **warning** (a sign on the door) for a hazard that needs a **control** (a door that won't open).

**Why these two specifically leak.** Both rules forbid without redirecting. When the build is broken and the only visible fix is in `src/generated/`, or when a rebase leaves the branch unpushable, the prohibition is competing with an active goal and offers no alternative route. Rules with a fallback vacuum get routed around under pressure — that's the shape of your 10%.

**What actually holds:**

1. **`PreToolUse` hook** on `Edit|Write`, exit code `2` when the path matches `src/generated/`. That blocks the call and returns your stderr message to Claude, which then has to find another path. Deterministic, and it logs every attempt so you learn the real rate instead of estimating it.
2. **`deny` rules in `settings.json`** — `Edit(src/generated/**)`, `Write(src/generated/**)`. Cheaper than a hook, no script to maintain.
3. **Force push needs a hook, not a deny string.** `Bash(git push --force*)` is prefix matching; `git push -f`, `git push origin +main`, and a `git config push.default` twist all slip past it. Parse the command in the hook instead.
4. **Branch protection on the remote** is the only true elimination for force push — it survives you, me, CI, and anyone's laptop. The hook is just a faster, friendlier failure.

**Then rewrite the CLAUDE.md lines as redirects, once each, no caps:**

> `src/generated/` is codegen output. To change it, edit `schema/*.graphql` and run `npm run codegen`. Direct edits are overwritten on the next build.

That gives the model the correct route, which is what the prohibition was missing.

`★ Insight ─────────────────────────────────────`
- Hook denials are strictly better feedback than silent compliance: a blocked call tells Claude *and* you that the wrong path was attempted, which surfaces the underlying pressure (broken codegen, bad rebase) instead of hiding it.
- Prohibitions without an alternative are the instruction-design equivalent of an unhandled error path.
`─────────────────────────────────────────────────`

Want me to write the two hooks and the deny rules? I'd need to know which repo the `src/generated/` rule belongs to — it isn't in the CLAUDE.md files loaded here — and whether you want `--force-with-lease` allowed through.