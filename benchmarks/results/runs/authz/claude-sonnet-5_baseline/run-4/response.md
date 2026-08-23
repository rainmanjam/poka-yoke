Good news and an important caveat, in that order.

**The caveat first:** this isn't application code — it's a benchmark eval fixture. The file's own header says so:

> `// The obvious path is scoped correctly. The hazards are in the places people forget: a nested resolver, a bulk export, an update path, and a tenant id taken from the client.`

`benchmarks/fixtures/documents.ts` lives in this repo's own skill-testing harness (`benchmarks/results/runs/agent-guardrails/...` grades against it). It's deliberately seeded with known tenant-isolation bugs to score whether an agent (with/without the poka-yoke skill) catches them. If your actual SOC2-scoped product has a file that looks like this, treat what follows as real findings — but if this is the only thing you pointed me at, it's not customer-facing risk, it's test data.

That said — you asked me to look, so here's what's actually in it, confirming your instinct was half right: the primary read path is scoped, the other paths aren't.

**Findings, worst first:**

1. **`exportWorkspace` (line 52-63) — critical, two stacked bugs.** `tenantId` comes from `req.body` (client-controlled, not session) and gets string-interpolated into raw SQL via `$queryRawUnsafe`. That's both a SQL-injection point and an IDOR — a caller can pass any `tenantId` and export another tenant's documents + comments, no auth check at all.

2. **`updateDocument` (line 41-50) — critical.** `db.documents.update({ where: { id: documentId }, ... })` has no `tenantId` in the where clause. Any authenticated user can overwrite any document by ID regardless of tenant. Writes are the classic blind spot — reviewers check reads and miss this.

3. **`searchDocuments` (line 65-73) — high.** `session` is accepted as a parameter and never used. The full-text query has no tenant filter, so search results leak titles/ranks across all tenants.

4. **`adminListDocuments` (line 75-78) — high.** Checks `session.userId` is truthy (authentication) but that's it — no tenant scoping, returns the latest 200 documents globally. "Admin" here means global admin, not admin-of-a-tenant.

5. **`Document.comments` / `Document.attachments` / `Document.author` resolvers (line 30-37) — medium, latent.** These nested GraphQL resolvers key off `parent.id`/`parent.authorId` with no tenant check of their own. Safe today only because the sole path to a `Document` parent is the correctly-scoped `document`/`documents` query — but nothing stops a future query or resolver from handing these a cross-tenant parent. The child inherits no scoping from the parent; it just happens to not be exploited yet.

**What's actually fine:** `getDocument` and `resolvers.Query.document`/`documents` (lines 14-26) filter by `session.tenantId` correctly — that's your "main path," and it is scoped.

**Root cause, if this were real code:** every one of these bugs is the same shape — a query that's one `WHERE tenantId = ?` short, in a place someone forgot. The device that closes all five at once isn't five separate fixes, it's making the unscoped call impossible to write: a `DocumentRepo` that requires a `tenantId` in its constructor (so raw `db.documents.*` is unreachable from handlers), plus Postgres RLS as the backstop for anything that slips past code review. Patching each site individually leaves the next nested resolver or bulk-export endpoint just as exposed.

Want me to check whether your actual production document-service code (not this fixture) has the same patterns?