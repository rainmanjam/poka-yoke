Read the file — this is a deliberately-seeded benchmark fixture (the header comment says as much: "the hazards are in the places people forget"), but every hazard it lists is real and worth walking through, since the shapes are exactly what would slip into production code too.

**Yes — five places let one tenant see or touch another's data.** Ranked by blast radius:

**1. `exportWorkspace` (line 52-63) — critical, two bugs stacked**
- `tenantId` is read from `req.body`, not from the session. Any authenticated caller can pass any tenant's ID and get that tenant's documents + comments back.
- It's also interpolated directly into raw SQL (`$queryRawUnsafe` with a template literal) — SQL injection, which on top of the tenant bug means an attacker doesn't even need to guess tenant IDs; they can break out of the string entirely.
- **Device:** never accept `tenantId` from the request — derive it from `session.tenantId` only. Use `$queryRaw` with parameterized bindings (tagged template, not string interpolation), never `$queryRawUnsafe` on user input.

**2. `updateDocument` (line 41-50) — critical**
- `where: { id: documentId }` has no `tenantId`. Any authenticated user who knows (or guesses) a document ID can overwrite another tenant's document — a cross-tenant write, not just a read.
- **Device:** `where: { id: documentId, tenantId: session.tenantId }`, same as `getDocument`. This is the one-line fix, but see the note below on why the one-line fix isn't the real fix.

**3. `searchDocuments` (line 65-73) — high**
- No `tenantId` filter at all. Full-text search runs across every tenant's documents; titles and rank leak cross-tenant.
- **Device:** add `AND tenant_id = ${session.tenantId}` to the query.

**4. `adminListDocuments` (line 75-78) — high**
- Checks `session.userId` is truthy (i.e., "is logged in"), not that the caller is actually an admin, and returns the 200 most recent documents across **all** tenants with no scoping at all. Any authenticated non-admin user hits this and gets a cross-tenant document feed.
- **Device:** check an actual admin/role claim, and if this is meant to be a per-tenant admin view, scope it like every other query; if it's meant to be a superadmin tool, it belongs behind separate infrastructure, not a shared handler reachable by tenant users.

**5. `Document.comments` / `Document.attachments` nested resolvers (line 29-35) — medium, currently latent**
- These trust `parent.id` and filter comments/attachments by `documentId` only — no independent tenant check. Right now they're only reached through `document`/`documents`, which *are* scoped, so this isn't exploitable through the code shown. But it's a fragile invariant: the moment any other code path constructs a `Document`-shaped parent (a dataloader, a batch resolver, a future field) without doing the tenant check itself, this silently becomes cross-tenant. Nested resolvers are exactly the blind spot the CLAUDE.md skill calls out — the parent got checked, the child inherits nothing.
- **Device:** scope by `tenantId` at the leaf too (`db.comments.findMany({ where: { documentId: parent.id, tenantId: ctx.session.tenantId } })`), don't rely on the parent having been checked.

**One more to watch:** `Document.author` (line 36-38) does `db.users.findUnique({ where: { id: parent.authorId } })` with no tenant check either. Whether that's a real leak depends on your data model — if users are tenant-scoped, this can return a user object belonging to a different tenant even though the document itself was scoped correctly.

**On "the main query paths are scoped so I think we're OK":** that's the trap this fixture is built to demonstrate — `getDocument` and `documents` are correct, and everything else drifted. Patching these five sites individually gets you to green today, but the same mistake is available at site #6 next sprint. Since you're prepping SOC2 evidence, the artifact worth having isn't "we fixed these five" — it's a **scoped repository** (tenant required in the constructor, so an unscoped query literally can't be written) plus a **cross-tenant test** that creates two tenants and asserts every operation from tenant A against tenant B's resources returns 404. That test is also better audit evidence than a diff, since it keeps proving isolation on every future PR instead of once.

Want me to implement the fixes (scoped repo + the two-tenant test) here, or is this fixture only meant to feed the detector/benchmark and the real target is elsewhere in the repo?