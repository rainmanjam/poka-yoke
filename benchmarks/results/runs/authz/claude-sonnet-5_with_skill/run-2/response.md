I did a fresh pass on `benchmarks/fixtures/documents.ts` (not from memory) using the poka-yoke `authz` audit method — walking every load-by-id, every write path, and every non-primary path (export/search/admin/nested resolvers), per that skill's checklist.

**Verdict: your instinct is wrong for four of the nine paths.** The primary GraphQL query paths (`getDocument`, `documents`) are correctly scoped by `session.tenantId`. But the write path, the export path, the search path, and the admin path all skip tenant scoping — and for SOC2 (CC6.1, logical access) these are exactly the "one customer sees another's data" findings an auditor looks for.

## Findings, ranked by blast radius × ease

### 1. `exportWorkspace` — tenant from request body + SQL injection — Critical/Trivial
**Where**: `documents.ts:52-63`
**Mistake**: `tenantId` is read from `req.body`, not from the authenticated session, and interpolated directly into raw SQL.
**Consequence**: Any caller can pass `{tenantId: "someone-elses-id"}` and export another tenant's entire document + comment set. Worse, the raw string interpolation (`'${tenantId}'`) is also SQL-injectable, so even a `tenantId` check added later could be bypassed with a crafted string. This is the single worst finding — full data exfiltration, no privilege needed beyond hitting the endpoint.
**Today**: None.
**Device**: Take `session: Session` instead of reading tenant from the body; use a parameterized query. → **Control**

### 2. `adminListDocuments` — checks login, not admin or tenant — Critical/Trivial
**Where**: `documents.ts:75-78`
**Mistake**: The only check is `session.userId` truthy — that's "is logged in," not "is an admin." The query has no `tenantId` filter at all and returns the 200 most recent documents across every tenant.
**Consequence**: Any authenticated user of any tenant can call this and read other tenants' recent documents.
**Today**: None (the auth check present is a decoy — it looks like a guard but checks the wrong thing).
**Device**: Verify an actual admin role/claim, and scope by `session.tenantId` even for admins (admin usually means admin *of a tenant*, per the skill). → **Control**

### 3. `updateDocument` — unscoped write — Critical/Trivial
**Where**: `documents.ts:41-50`
**Mistake**: `session` is accepted as a parameter but never used. The `where` clause is `{ id: documentId }` only.
**Consequence**: Any tenant can overwrite any other tenant's document title/body by ID. This is a write, so it's worse than a read leak — it's cross-tenant data corruption, and it's silent (no error, looks like a normal successful update).
**Today**: None. Note the signature itself is a hazard — `session` sitting unused in the argument list looks like it's doing authorization work and isn't.
**Device**: `where: { id: documentId, tenantId: session.tenantId }`. → **Control**

### 4. `searchDocuments` — unscoped read despite taking `session` — High/Trivial
**Where**: `documents.ts:65-73`
**Mistake**: Takes `session: Session` (implying it should scope) but the SQL has no `tenant_id` predicate.
**Consequence**: Any user can search and see titles (and existence) of documents belonging to every tenant.
**Today**: None.
**Device**: Add `AND tenant_id = ${session.tenantId}` to the query. → **Control**

### 5. `Document.author` nested resolver — cross-tenant user fetch — Medium
**Where**: `documents.ts:36-37`
**Mistake**: Loads `db.users.findUnique({ where: { id: parent.authorId } })` with no tenant check.
**Consequence**: Currently only reached from tenant-scoped parents, so it's not independently exploitable *today* — but it provides zero enforcement of its own. The moment any of findings 1–4 feed a Document into this resolver (or a new one does), it will hand back the author's user record cross-tenant.
**Today**: None — it's relying entirely on the parent having been safe.
**Device**: Scope by tenant on the users table too, or pass tenant context through the resolver chain. → **Control** (or accept as intentional if `users` is a genuinely cross-tenant table — worth confirming, don't assume).

### 6. `Document.comments` / `Document.attachments` nested resolvers — Low (today), landmine (soon)
**Where**: `documents.ts:30-34`
**Mistake**: Both load by `documentId: parent.id` alone — no independent tenant check, just inherited trust in the parent.
**Consequence**: Same shape as #5 — safe only because every current path to a `Document` happens to be scoped. This is exactly the "nested resolvers inherit nothing" blind spot the skill calls out, and this file already has three broken document sources (#1, #2, #4) that could feed it.
**Device**: If these resolvers are ever reachable independently of the parent's own auth, add the tenant predicate directly rather than trusting the caller. Lower priority than 1–4 since not independently reachable right now.

## Set aside
`getDocument` and `resolvers.Query.documents` — both correctly scoped, no finding.

I haven't changed anything — per the audit skill, findings get proposed first. Want me to apply the fixes for 1–4 (the ones with real, current exploit paths), and/or write this up as `docs/poka-yoke/audit-2026-08-22.md` so you have a dated artifact for the SOC2 evidence trail?