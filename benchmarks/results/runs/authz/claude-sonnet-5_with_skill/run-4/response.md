Using the poka-yoke `authz` skill to audit this fixture, since the ask is exactly "can users see each other's data" / tenant isolation review.

Your instinct on the main paths is right — `getDocument` and the `documents` query both filter by `session.tenantId`, which comes from the session, not the request. But that's 2 of 8 exported functions/resolvers. The other 6 either drop the tenant filter, take the tenant ID from the client, or don't check it at all. Ranked by blast radius:

**1. `exportWorkspace` (line 52-63) — critical, and it's two bugs stacked**
`tenantId` comes from `req.body`, so it's client-controlled — any authenticated user can request another tenant's export by changing one field. Worse, it's interpolated directly into raw SQL (`$queryRawUnsafe`, string template), so it's also classic SQL injection — a crafted `tenantId` value breaks out of the `WHERE` clause entirely. This is the one an auditor would flag hardest: bulk export + cross-tenant + injectable, all in one function.
*Device:* take `tenantId` from `session`, never `req.body`; drop `$queryRawUnsafe` for a parameterized query or the query builder. Control rung, cheap.

**2. `adminListDocuments` (line 75-78) — critical**
Checks `session.userId` is truthy (i.e., "someone is logged in") and nothing else. Returns the 200 most recent documents across every tenant. The name "admin" is doing the work a permission check should be doing — this is the exact hazard the skill calls out: "admin" usually means admin *of a tenant*, and a global query in a tenant-facing surface is a leak.
*Device:* scope by `session.tenantId` like the other reads, or if this is genuinely a platform-admin tool, it needs its own auth path that isn't reachable from tenant sessions at all.

**3. `searchDocuments` (line 65-73) — critical**
Raw SQL full-text search with no `tenant_id` predicate anywhere. Any authenticated user can search and get back titles (and rank) from every other tenant's documents. `session` is even passed in as a parameter and never used.
*Device:* add `AND tenant_id = ${session.tenantId}` to the query.

**4. `updateDocument` (line 41-50) — critical, and it's a write**
`where: { id: documentId }` — no tenant filter. Any authenticated user can update any other tenant's document by ID. This is the one the skill specifically warns gets missed: "reads get the attention; writes get missed." `session` is passed in and, again, never used in the query.
*Device:* `where: { id: documentId, tenantId: session.tenantId }`. If you want a distinguishable "not found vs. not yours" story, that's still the constraint — you just also want the row-count/updated check to confirm a match happened (Prisma's `update` throws if no row matches, which is actually fine here — it'll error rather than silently updating nothing, so this is at least self-announcing once fixed, just not scoped yet).

**5. `Document.comments` / `Document.attachments` nested resolvers (line 29-34) — high**
Both scope only by `documentId`, with no tenant check. Since the parent `document` query is scoped, the direct path is safe — but nested GraphQL resolvers don't inherit the parent's scoping, they inherit nothing. If `documentId` is guessable/enumerable (sequential ID, or leaked via `exportWorkspace`/`searchDocuments` above), a user can request `comments`/`attachments` for a document ID belonging to another tenant, and this resolver will happily return it. This is exactly the "child inherits nothing" hazard the skill names.
*Device:* verify `parent.tenantId === ctx.session.tenantId` in the resolver, or better, have the parent resolver attach a branded/pre-authorized document object so the child literally cannot be called with a cross-tenant parent.

**6. `Document.author` (line 36-37) — medium**
Unscoped `findUnique` by `authorId`. Lower blast radius (returns a user record, not tenant data), but still worth closing for the same reason as above — it's a lookup with no ownership check at all.

**For the audit specifically:** the two-tenant test the skill recommends is the thing to point to in evidence — create two tenants, run every one of these 8 paths from tenant A against tenant B's document, assert 404 across the board. Right now that test would fail on 6 of 8. I'd write that test first (Detection rung, proves the gap), then fix the 6, then keep the test as the regression guard — that's the artifact a SOC2 auditor actually wants to see: not just "we fixed it" but "here's the test that would have caught it and still runs."

I haven't changed anything — want me to go ahead and fix these (scoping + the injection), and/or write the two-tenant test?