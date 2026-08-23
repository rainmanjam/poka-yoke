Good news: your instinct about the primary paths is right — `getDocument` and the `documents`/`document` resolvers all filter by `session.tenantId`. But there are **6 real cross-tenant holes** in this file, and given this is going into a SOC2 audit, all of these need fixing first. Ranked by blast radius:

**1. `exportWorkspace` — client-controlled tenant + SQL injection (critical)**
```ts
const { tenantId, format } = req.body;
db.$queryRawUnsafe(`... WHERE d.tenant_id = '${tenantId}'`)
```
`tenantId` comes from the request body, not the session — any authenticated user can pass someone else's tenant ID and export their documents+comments. It's also raw string interpolation into SQL, so it's *also* injectable (`tenantId: "' OR '1'='1"` dumps every tenant, or worse). Two independent ways to read all customer data through one endpoint.
→ Fix: derive tenant from `session`/auth context, never `req.body`. Use a parameterized query, not `$queryRawUnsafe` with interpolation.

**2. `adminListDocuments` — "admin" check that isn't one (critical)**
```ts
if (!session.userId) throw new Error("unauthenticated");
return db.documents.findMany({ orderBy: { createdAt: "desc" }, take: 200 });
```
This only checks the caller is *logged in*, not that they're an admin, and it has no `tenantId` filter at all. Any authenticated user of any tenant sees the 200 most recent documents across every tenant.
→ Fix: check an actual admin/role claim, and scope even the admin view to the admin's own tenant (or explicitly to a superadmin role with its own audit trail, if cross-tenant admin access is a real product requirement).

**3. `updateDocument` — write path has no tenant filter (critical)**
```ts
db.documents.update({ where: { id: documentId }, data: patch })
```
`session` is passed in but never used. Any user can overwrite any document in any tenant just by knowing/guessing its ID. This is worse than a read leak — it's cross-tenant data corruption.
→ Fix: `where: { id: documentId, tenantId: session.tenantId }`.

**4. `searchDocuments` — global full-text search (high)**
```ts
db.$queryRaw`SELECT id, title, ... FROM documents WHERE search_vector @@ plainto_tsquery(${query}) ...`
```
`session` is accepted but unused. Search results are returned across all tenants.
→ Fix: add `AND tenant_id = ${session.tenantId}` to the query.

**5. `Document.author` resolver — global user lookup (medium-high)**
```ts
author: (parent: { authorId: string }) => db.users.findUnique({ where: { id: parent.authorId } })
```
No tenant check at all — it trusts `parent.authorId` and fetches any user record globally. If users carry any tenant-scoped PII (email, phone, internal notes), this leaks it cross-tenant, and it doesn't even require the attacker to guess a document ID belonging to another tenant if `authorId` is ever attacker-influenced.
→ Fix: scope by tenant, e.g. `db.users.findFirst({ where: { id: parent.authorId, tenantId: ctx.session.tenantId } })`, or better, pass tenant context down and use a scoped repo.

**6. `Document.comments` / `Document.attachments` resolvers — scoped only by inheritance (medium)**
```ts
comments: (parent) => db.comments.findMany({ where: { documentId: parent.id } })
```
These aren't tenant-scoped themselves — they're safe *today* only because the only caller (`Query.document`) already checked tenant on the parent. That's fragile: any future resolver, batch loader, or dataloader that fetches a `Document` by ID without the tenant check (there's already precedent for that pattern in this file — see `updateDocument`) will silently make these leak too.
→ Fix: add `tenantId` to these `where` clauses as well, even though it's currently redundant. Nested resolvers should never rely on the parent having done the check.

**Bottom line:** the "main query paths" (get/list) are fine, but the update, export, search, admin, and nested-resolver paths are not — and those are exactly the categories that get missed in review and then show up in a SOC2 finding. If you want, I can turn these into a `db.tenantScoped(session.tenantId)` scoped-repo wrapper so the unscoped form (`db.documents.*` directly) is no longer reachable from any of these handlers — that closes all six at once rather than patching each `where` clause individually. Want me to do that?