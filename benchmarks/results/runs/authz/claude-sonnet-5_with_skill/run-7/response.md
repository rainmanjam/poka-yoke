Used the `poka-yoke:authz` skill to audit this — it's built exactly for "can one tenant see another's data." Short answer: **no, you're not okay.** The two obvious paths (`getDocument`, `documents` list) are scoped correctly, but I count four live cross-tenant holes and one latent one, ranked by blast radius:

**1. `exportWorkspace` — critical, and worse than an IDOR**
`tenantId` comes from `req.body`, not `session` — the function doesn't even take a `Session` argument. Any caller can request `{ tenantId: "some-other-tenant-uuid" }` and get that tenant's full documents + comments back. It's also built with `$queryRawUnsafe` and raw string interpolation of `tenantId` into SQL, so it's SQL-injectable on top of that — an attacker doesn't even need a real tenant ID, they can break out of the filter entirely. This is the one an auditor would flag first: unauthenticated cross-tenant export plus injection.
*Device:* drop `tenantId` from the request body, take it from an authenticated `Session`, and switch to `db.$queryRaw` with parameterized values. That's Control rung — the wrong tenant literally can't be expressed.

**2. `searchDocuments` — critical**
It receives `session` but never uses it. The raw SQL only filters on `search_vector @@ plainto_tsquery(...)` — no `tenant_id` predicate — so full-text search returns matches from every tenant.
*Device:* add `AND tenant_id = ${session.tenantId}` to the query. Control rung, one-line fix, but exactly the kind of one-liner that's invisible in review — worth a two-tenant test (below) so it can't regress silently.

**3. `adminListDocuments` — critical, and the "admin" check is fake**
The guard is `if (!session.userId) throw ...` — that's "is logged in," not "is an admin," and there's no tenant filter on the `findMany` either. Any authenticated user of any tenant gets the 200 most recent documents across *all* tenants.
*Device:* if it's meant to be tenant-scoped admin, add `where: { tenantId: session.tenantId }` and a real role check. If it's meant to be a genuine cross-tenant support tool, it needs a separate authorization type (e.g. `Owned<GlobalAdmin>` per the authz skill's "authorization in the type" pattern) — not a truthy-userId check — plus an audit log, since that's a deliberately dangerous capability.

**4. `updateDocument` — critical write path**
`db.documents.update({ where: { id: documentId }, data: patch })` — `session` is a parameter but never touches the query. Any authenticated user can overwrite the title/body of any document in any tenant by ID.
*Device:* `where: { id: documentId, tenantId: session.tenantId }`. Note this needs a compound unique constraint (`@@unique([id, tenantId])`) for Prisma's `update` to accept a compound `where`, or switch to `updateMany` + assert the returned count is 1 (if 0, treat as 404 — not authorization failure, per the skill's "404 not 403" rule).

**5. `Document.comments` / `Document.author` nested resolvers — latent today, live once you fix #2/#3**
Both resolvers trust `parent` unconditionally: `comments` filters only by `documentId`, `author` does a global `findUnique` by `authorId`, neither checks tenant. Right now they're only reachable via the scoped `document`/`documents` queries, so they ride on the parent's correctness. But #2 and #3 return unscoped `Document` objects — if those ever go through the same GraphQL `Document` type (or once someone adds a third path), the comments/attachments/author fields leak cross-tenant with zero additional effort. This is the "nested resolver inherits nothing" trap called out specifically in the authz skill.
*Device:* the resolvers should take tenant from `ctx.session`, not trust `parent`, e.g. `db.comments.findMany({ where: { documentId: parent.id, tenantId: ctx.session.tenantId } })`.

**Why the main paths look fine and hide this:** every broken function *takes* `session` (or claims to check auth) but doesn't *use* it to scope the query — that's the exact "unsafe is the short form" trap the skill describes. A reviewer skimming signatures would see `session: Session` as a parameter and assume it's doing its job.

**What I'd install, not just fix:** a two-tenant test — create tenant A and B, run every exported function/resolver here with A's session against B's document IDs, assert 404/empty for all of them, table-driven over the function list so a new export without a case fails the suite. That's a Detection-rung backstop that would have caught all five of these, and it catches the next one too.

I haven't touched the file — want me to apply these five fixes, or write the two-tenant test first so you can watch it go red on the current code before I patch it?