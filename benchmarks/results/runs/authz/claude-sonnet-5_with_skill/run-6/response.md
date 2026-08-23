Your instinct is wrong on the scope — the "main" query paths (`getDocument`, the `document`/`documents` resolvers) are correctly scoped, but there are **four real cross-tenant paths** in this file, plus two nested-resolver hazards. This is not audit-ready for SOC2 as-is.

**Verdict**: `updateDocument`, `exportWorkspace`, `searchDocuments`, and `adminListDocuments` all bypass tenant scoping — three of them (export, search, admin-list) let one tenant read another's documents, and `updateDocument` lets one tenant **write** another's document. `exportWorkspace` additionally has a SQL injection hole.

## Findings

### 1. `updateDocument` never checks tenant — cross-tenant write — Critical/Silent
**Where**: `benchmarks/fixtures/documents.ts:41-50`
**Mistake**: Any authenticated user in tenant A calls `updateDocument(session, <tenant B's documentId>, patch)`. `session` is accepted as a parameter but never referenced in the query.
**Consequence**: `db.documents.update({ where: { id: documentId }, data: patch })` updates the row regardless of owner. Tenant A silently overwrites tenant B's document — no error, no signal, plausible-looking success.
**Today**: None.
**Device (Control)**: `where: { id: documentId, tenantId: session.tenantId }` — same fix pattern as `getDocument` two functions above it. Better: route this through a `DocumentRepo` constructed with `session.tenantId` so an unscoped `.update()` isn't reachable at all (per `authz` skill's "scoped repository" device).

### 2. `exportWorkspace` takes `tenantId` from the request body, and interpolates it into raw SQL — Critical/Silent + SQLi
**Where**: `benchmarks/fixtures/documents.ts:52-63`
**Mistake**: `const { tenantId, format } = req.body` — tenant identity comes from client input, not the session, and this function doesn't even take a `session`/auth context. Any caller can export any tenant's full document + comment set by supplying its `tenantId`.
**Consequence**: Full bulk data exfiltration across tenants. Worse, `tenantId` is spliced directly into `$queryRawUnsafe` (`WHERE d.tenant_id = '${tenantId}'`) — that's also a SQL injection vector, since `tenantId` is attacker-controlled.
**Today**: None.
**Device (Control)**: Take `session: Session` as the parameter, derive tenant from `session.tenantId`, drop `req.body.tenantId` entirely, and use a parameterized query (`db.$queryRaw` with tagged template, not `$queryRawUnsafe` with interpolation) — same pattern already used correctly in `searchDocuments`'s query construction.

### 3. `searchDocuments` accepts `session` but never filters by it — Critical/Silent
**Where**: `benchmarks/fixtures/documents.ts:65-73`
**Mistake**: The SQL has no `tenant_id` predicate at all — search runs over every tenant's documents.
**Consequence**: Any user's search returns titles (and ranks) of other tenants' documents. Silent — looks like a working search feature.
**Today**: None.
**Device (Control)**: Add `AND tenant_id = ${session.tenantId}` to the WHERE clause.

### 4. `adminListDocuments` checks authentication, not tenant — Critical/Silent
**Where**: `benchmarks/fixtures/documents.ts:75-78`
**Mistake**: `if (!session.userId) throw` only proves *someone* is logged in — not that they're an admin, and not that results are scoped to their tenant. The query itself (`findMany({ orderBy, take: 200 })`) has no `where` clause at all.
**Consequence**: Any authenticated user from any tenant can list up to 200 documents across every tenant.
**Today**: Warning-adjacent at best (auth check exists, authz check doesn't).
**Device (Control)**: Add both an actual admin-role check and `where: { tenantId: session.tenantId }` — "admin" here should mean admin *of a tenant*, per the `authz` skill's point #5.

### 5. `Document.comments` / `Document.attachments` nested resolvers — Medium/Latent
**Where**: `benchmarks/fixtures/documents.ts:30-34`
**Mistake**: Both resolve `where: { documentId: parent.id }` with no tenant check — they trust that `parent` was already tenant-scoped.
**Consequence**: Not currently exploitable via the `document`/`documents` queries (those are scoped, so `parent` can only be a document you already own), but it's a landmine: the moment any new resolver returns a `Document` object without going through the scoped path (e.g., wiring `searchDocuments`'s raw rows into the `Document` GraphQL type, which is a very plausible next PR given finding #3), comments and attachments leak with zero additional code.
**Device (Warning now, Control eventually)**: Scope these too — `where: { documentId: parent.id, document: { tenantId: ctx.session.tenantId } }` (or equivalent) — so the resolver is safe independent of how `parent` was obtained. This is exactly the "child inherits nothing" trap the `authz` skill calls out by name.

## Set aside
- `Document.author` (`db.users.findUnique({ where: { id: parent.authorId } })`) — unscoped by tenant, but `authorId` is only ever a same-tenant user (it comes from an already-scoped document), so no cross-tenant path today. Worth the same defensive fix as #5 if you ever expose author lookup elsewhere, but lower priority.

**Bottom line for the audit**: 4 of 7 exported functions in this file bypass tenant scoping, and one of those also has a SQL injection bug. If this fixture reflects real code, none of `updateDocument`, `exportWorkspace`, `searchDocuments`, or `adminListDocuments` should ship to your SOC2 auditor as-is — I'd fix all four before the audit, not just document them as known findings, since "one tenant can read/write another's data" is the exact CC6.1/CC6.6 finding that turns an audit into a qualified opinion.

Want me to apply the fixes (scoped `where` clauses, session-derived tenant on export, parameterized SQL) directly to this file?