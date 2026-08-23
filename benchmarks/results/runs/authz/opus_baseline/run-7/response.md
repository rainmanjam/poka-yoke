Two things before the findings.

**This file is an eval fixture, not your production service.** Line 1–4 says so, and it imports a `./db` that doesn't exist in that directory. The hazards in it are planted on purpose — it's the input to `benchmarks/` for testing whether the authz skill finds them. So none of this is a live exposure, and none of it belongs in your SOC2 evidence. Treat the list below as the checklist to run against the *real* document service. (I couldn't run `detect_hazards.py` — needs approval — but these are all semantic, not grep-shaped, so it wouldn't have caught them anyway.)

**Your premise is half right.** `getDocument` and the `documents` query *are* correctly scoped. But six other paths aren't, and they're all the same omission those two happened to remember.

## Findings, worst first

**1. `exportWorkspace` (52–63) — full workspace dump, any tenant.** `tenantId` comes from `req.body` — client-controlled. Post someone else's tenant ID, get every document and comment. And it's string-interpolated into raw SQL, so `' OR '1'='1` drops the predicate entirely. It also never reads a session, so it may be reachable unauthenticated. Three bugs stacked.

**2. `adminListDocuments` (75–78) — no scope, no admin check.** `if (!session.userId)` is a *login* check. Any authenticated user of any tenant gets the 200 most recent documents globally. "Admin" almost always means admin *of a tenant*.

**3. `updateDocument` (41–50) — cross-tenant write.** `where: { id }` with no tenant. Tenant A can overwrite B's title and body. Writes get less review attention than reads and are worse when wrong.

**4. `searchDocuments` (65–73) — searches every tenant.** Takes `session` and never uses it. The tagged template is parameterized so there's no injection, but the predicate is simply absent. Returns ids + titles — titles leak plenty on their own, and the ids feed finding 3. The unused parameter is the tell; ESLint `no-unused-vars` on args would flag this shape.

**5. Nested resolvers `comments` / `attachments` (29–34).** Scoped by `parent.id`, which carries no authorization. Safe *only* while every path returning a `Document` is scoped. That's an invariant nobody can see, and finding 4 already violates it.

**6. `author` (36–37).** Unscoped `findUnique` on users, returning the whole row. Whatever your `User` type exposes is reachable from any document.

## The device, not six patches

Adding `tenantId` to six queries fixes six sites and leaves the seventh writable. Rungs, strongest first:

- **Postgres RLS** with `FORCE ROW LEVEL SECURITY`, `app.tenant_id` set per-transaction by the only middleware that hands out connections. This is the one that also covers scripts, migrations, and code you haven't written.
- **A scoped repo** taking `TenantId` as a required constructor arg, with the raw client lint-banned from handler files.
- **A two-tenant test** — every operation from A against B's resources, asserting 404 (not 403 — 403 confirms existence). Table-driven over the route list so a new endpoint without a case fails.

★ Insight ─────────────────────────────────────
The reason `updateDocument` is worth its own decision: Prisma's `update` requires a *unique* where. You can't just add `tenantId` to it. Two options — `updateMany({ where: { id, tenantId } })` and assert `count === 1`, or a `@@unique([id, tenantId])` compound index so `update` takes `{ id_tenantId: {...} }`. The second is stronger: it makes the unscoped form a **type error**, not a code-review catch. That's the difference between rung 2 and rung 4.
─────────────────────────────────────────────────

One thing I need from you before going further: **is the real service on Postgres with a connection pool?** If yes, RLS is the right first move and the pooling detail is where it lives or dies. If you're on something without RLS, the scoped repo becomes the primary device and the answer looks different.