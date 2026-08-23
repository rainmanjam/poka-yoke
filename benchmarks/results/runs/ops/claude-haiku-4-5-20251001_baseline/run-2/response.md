**Yes, with one caveat: only if you can rollback the schema change independently if the code deploy has issues.**

The main Friday afternoon risk isn't the change itself (small, tested, removes dead code) — it's the support window. If something unexpected happens post-deploy, your response time is constrained.

Before you push, verify:

1. **Schema rollback is clean** — Can you drop the column, need to restore it? Most migration tools make this straightforward (`down` migration), but confirm yours does. If rolling back requires manual SQL, document it.

2. **No cross-service dependencies** — You said "3 places in the code" that read it. Are those all in this service, or does any other service or job still reference `legacy_email`? (Search logs, scheduled jobs, webhooks, data exports if any exist.)

3. **The code deploy is truly the only change** — This is on `feat/multi-runtime-and-brand`, which sounds like a bigger branch. Is this column-drop the only schema change in this PR? If there are other migrations stacked, Friday afternoon gets riskier.

If all three check out, you're good. Small, isolated schema removals with all code paths updated are boring in the best way.

What's your rollback plan if you need it?