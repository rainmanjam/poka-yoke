Read it in full. **No — you're not ok. There are six cross-tenant paths**, and your instinct is right in a way that's actually the trap: `getDocument`, `Query.document`, and `Query.documents` *are* correctly scoped. Those are the paths people audit. Every hazard is somewhere else.

**First, a scope correction:** this is an eval fixture, not shipping code. Its own header says hazards are planted in it, `./db` doesn't exist so it can't compile, and `benchmarks/scenarios.json:79` uses it as benchmark input. It is **not in SOC2 scope**, and editing it in place would void the benchmark runs recorded against it. Treat the list below as the checklist to run against your real document service.

## Findings, worst first

**1. `exportWorkspace` — tenant ID from the client + SQL injection (`documents.ts:52-63`)**
`const { tenantId } = req.body` — the caller names the tenant they want. There's no `Session` parameter at all, so nothing authenticates the request. Worse, `tenantId` is string-interpolated into `$queryRawUnsafe`, so `' OR '1'='1` dumps documents *and* joined comment bodies for every tenant. Two independent full-database reads in one function. Tenant must come from the session; the raw string interpolation should not survive at all.

**2. `adminListDocuments` — authentication mistaken for authorization (`documents.ts:75-78`)**
`if (!session.userId)` proves someone is logged in, not that they may see anything. The query is unscoped, so *any* authenticated user of *any* tenant gets the 200 most recent documents globally. "Admin" here checks no role and no tenant.

**3. `updateDocument` — cross-tenant write (`documents.ts:41-50`)**
`where: { id: documentId }`, no `tenantId`. Any user can overwrite any document's title/body. Note the Prisma detail: you can't just add `tenantId` to `update`'s where unless there's a compound unique — use `updateMany({ where: { id, tenantId } })` and assert `count === 1`, or add the compound unique index.

**4. `searchDocuments` — takes `session`, never uses it (`documents.ts:65-73`)**
No tenant predicate. Full-text search over every tenant's documents, returning titles — which routinely carry customer and deal names. **Chain it with #3:** search hands you another tenant's document IDs, `updateDocument` lets you write to them.

**5. Nested resolvers inherit nothing (`documents.ts:30-34`)**
`comments` and `attachments` scope only by `documentId: parent.id`. Via `Query.document` the parent was tenant-checked, so this is safe *today* — it's latent, and it detonates the moment any unscoped path produces a `Document` parent. Scope children by tenant directly rather than trusting the parent.

**6. `author` returns the whole user row (`documents.ts:36-37`)**
`findUnique` with no tenant scope and no field selection — leaks every user column, including whatever PII and credential material that table holds.

`★ Insight ─────────────────────────────────────`
Notice the pattern: reads on the primary path got scoped, and the write path, the export, the search, and the nested field did not. Blanket-adding six `where` clauses fixes these six sites and does nothing about the seventh someone writes next sprint — the hazard is that `db` is reachable from every handler, so the unscoped query is the *shorter* thing to type.
`─────────────────────────────────────────────────`

## What actually closes this

A `where` clause per site is the Training rung. Two devices reach Control: **Postgres RLS** (`ENABLE` + `FORCE ROW LEVEL SECURITY`, policy on `current_setting('app.tenant_id')`, set per-transaction — a pooled connection carrying the previous request's setting is a leak with extra steps), and a **scoped repository** whose constructor requires a `TenantId`, with the raw `db` client lint-banned from handler code.

Then the test that proves it: create two tenants, run every operation from A against B's resources, assert **404 not 403** — a 403 confirms the row exists. Table-drive it over your route list so a new endpoint with no isolation case fails rather than passes silently.

**One thing I can't decide for you:** does `exportWorkspace` have a legitimate cross-tenant caller — a support or billing tool that really does need to export on someone's behalf? If yes, the fix isn't "scope it to the session," it's a separately-authenticated admin path with its own audit log, and that changes the shape. If you tell me which, I'll write the scoped version against your real service.