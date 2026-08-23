## First, the thing that changes what you should do with this

`benchmarks/fixtures/documents.ts` is not production code — it's the answer key for your own authz eval. It's referenced only by `benchmarks/results/runs/authz/*` and `poka-yoke-workspace/iteration-2/authz-tenant-isolation/`, its `./db` import doesn't resolve to anything, and the header comment names the planted hazards. **Don't fix it** — you'd invalidate the benchmark. Your auditor won't look at it either.

That said, the findings are real and worth holding your actual document service against. Six of them, ranked:

**1. `adminListDocuments` (75-78)** — no tenant predicate at all, and the guard is `if (!session.userId)`, which is authentication, not authorization. Any logged-in user of any tenant gets 200 documents across the whole estate. "Admin" almost always means admin *of a tenant*.

**2. `exportWorkspace` (52-63)** — `tenantId` comes from `req.body`. The session is never consulted. It's also interpolated into `$queryRawUnsafe`, so `tenantId: "' OR '1'='1"` drops the predicate entirely. Broken authz and injection stacked on the same line.

**3. `searchDocuments` (65-73)** — takes `session` and never uses it. Full-text search across every tenant's documents. Titles alone are disclosure.

**4. `updateDocument` (41-50)** — `where: { id }`, no tenant. Cross-tenant *write*. This is the canonical miss: reads get reviewed, writes don't.

**5. Nested resolvers `comments` / `attachments` (30-34)** — scoped by `documentId` only. The parent was checked; the children inherit nothing. Safe today only because every path to a `Document` happens to be scoped — that's an invariant nobody is enforcing.

**6. `author` (36-37)** — `findUnique` by `authorId` with no scope and no field selection. Whatever your `User` GraphQL type exposes, a cross-tenant author resolves it.

## The one you didn't plant

`getDocument` and the `documents` query look correct, and they are — until `session.tenantId` is `undefined`. Prisma **drops undefined keys from `where`**, so a malformed session silently turns `findFirst({ id, tenantId: undefined })` into an unscoped lookup by ID. The correct paths fail open. Worth grepping your real code for anywhere a session field can be optional.

`★ Insight ─────────────────────────────────────`
Every one of these six is *reachable* because `db` is importable in handler code. The `where` clauses are symptoms; the device is that a handler should have no way to reach an unscoped client. RLS with `FORCE ROW LEVEL SECURITY` is the only rung that also covers migrations, scripts, and the psql shell your auditor will ask about.
`─────────────────────────────────────────────────`

## For the audit itself

The evidence SOC2 wants isn't a clean read of this file — it's a **two-tenant test matrix**: create tenants A and B, attempt every route from A against B's resources, assert **404 for all** (403 confirms existence and leaks membership). Table-drive it over your route list so a new endpoint without a case fails rather than passes silently.

Want me to look at your real document service, or draft that isolation test harness? I'd need a pointer to the actual repo — `payments.ts` next door is the other fixture, not production.