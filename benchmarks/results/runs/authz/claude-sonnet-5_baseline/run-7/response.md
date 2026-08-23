I read `benchmarks/fixtures/documents.ts` (79 lines) directly — small enough that no sandboxing was needed. Your instinct on the main query paths is right, but there are four real cross-tenant holes here, ranked by severity:

## Confirmed leaks

**1. `searchDocuments` (line 65-73) — no tenant filter at all**
```ts
export async function searchDocuments(session: Session, query: string) {
  return db.$queryRaw`SELECT id, title, ... FROM documents WHERE search_vector @@ plainto_tsquery(${query}) ...`
```
`session` is accepted as a parameter and never used. Any authenticated user can full-text-search every tenant's document titles. **Fix:** add `AND tenant_id = ${session.tenantId}` — but better, route this through a scoped repo (device #2 in the skill) so the raw client isn't reachable from this handler at all.

**2. `exportWorkspace` (line 52-63) — tenant id from the request body, plus SQL injection**
```ts
const { tenantId, format } = req.body;
... `WHERE d.tenant_id = '${tenantId}'`
```
Two independent bugs stacked: the tenant boundary is client-supplied (attacker just puts a different `tenantId` in the JSON body), and it's string-interpolated into `$queryRawUnsafe`, so even that check can be bypassed entirely with `' OR '1'='1`. This is a full workspace dump of any tenant, trivially. **Fix:** `tenantId` must come from `session`, never `req.body`; use parameterized queries, not `$queryRawUnsafe`.

**3. `updateDocument` (line 41-50) — write path unscoped**
```ts
return db.documents.update({ where: { id: documentId }, data: patch });
```
`session` is passed in but never checked against the row. Any tenant can overwrite any other tenant's document by ID. This is the one people miss because reads get reviewed and writes don't — exactly the pattern the skill calls out. **Fix:** `where: { id: documentId, tenantId: session.tenantId }` (Prisma will throw/no-op if the compound condition doesn't match, which is the correct "not found" behavior rather than "found but for the wrong tenant").

**4. `adminListDocuments` (line 75-78) — "admin" check that isn't one, and global scope**
```ts
if (!session.userId) throw new Error("unauthenticated");
return db.documents.findMany({ orderBy: { createdAt: "desc" }, take: 200 });
```
The guard only checks that *someone* is logged in, not that they're an admin — and even if it were a real admin check, it returns the 200 most recent documents across **all** tenants. Any authenticated user hits this and sees every tenant's newest documents. **Fix:** check an actual admin role/claim, and scope to the admin's own tenant unless this is meant to be a superadmin-only tool behind separate infra.

## Secondary, lower severity

**`Document.comments` / `Document.attachments` resolvers (line 29-34)** — scoped only by `documentId`, not tenant. Currently safe in isolation because the only paths that produce a `parent` Document are correctly tenant-scoped (`getDocument`, `documents`) — but that safety is inherited, not enforced. If `adminListDocuments`'s unscoped documents ever flow through the `Document` GraphQL type (likely, since it's the same shape), these resolvers become the exfiltration path for comments/attachments across tenants. Same root cause as #4, not a separate bug, but worth closing so the resolver doesn't *rely* on every caller upstream doing the right thing.

**`Document.author` (line 36-37)** — looks up `db.users.findUnique({ where: { id: parent.authorId } })` with no tenant check. Same inherited-safety issue as above; becomes a PII leak (author email/name) the moment an unscoped Document reaches this resolver.

## Bottom line for the audit

The "obvious path" — `getDocument`, `resolvers.Query.document`, `resolvers.Query.documents` — is correctly scoped by `session.tenantId` and fine as-is. But 4 of 8 functions in this file have no effective tenant boundary, and one of those (`exportWorkspace`) also has a SQL injection. If this fixture reflects real code, "the main paths are scoped" isn't the finding a SOC2 auditor needs — the export, search, admin-list, and update paths are the ones that'll get flagged.

Per the skill's recommendation: the durable fix isn't patching these four `where` clauses (that just fixes these four call sites) — it's making the raw `db` client unreachable from handler code, via a `DocumentRepo` constructed with a required `tenant: TenantId`, plus a two-tenant isolation test that asserts 404 across every exported function here. Want me to build that scoped repo and the isolation test now?