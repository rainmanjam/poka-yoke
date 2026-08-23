Small change + green CI is good, but Friday afternoon deployments hinge on a few things I'd verify first:

1. **Data migration safety** — When you dropped `legacy_email`, did you run a backfill/verification query to confirm no production rows still need it? A column drop is instant but irreversible, so "we updated the three places" is only half the story if something else queries it at runtime.

2. **Rollback window** — If something breaks post-deploy, how long until someone can roll back? Friday afternoon into evening means a narrow window before oncall context switches.

3. **Downstream services** — Does anything outside this service (webhooks, other services reading this table, old API clients) still reference `legacy_email`? The three code paths you updated might not be exhaustive.

4. **Deployment procedure** — Is this a standard blue-green / canary, or a direct deploy? Column drops can be invisible until a query hits it under load.

**Quick take:** If (1) you've verified no stray queries reference it, (2) rollback is <5 minutes, and (3) you've checked downstream, it's low-risk enough for Friday afternoon. Otherwise, queue it for Monday morning and let the weekend be quiet.

What does your deployment process look like, and have you verified the data side?