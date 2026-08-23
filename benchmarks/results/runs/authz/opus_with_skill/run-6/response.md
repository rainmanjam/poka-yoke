I couldn't write the report to a file (permission denied in this session), so it's inline below.

**First, the thing that changes what this answer is worth:** `benchmarks/fixtures/documents.ts` is a benchmark eval fixture in this repo, and its own header says the hazards are planted on purpose. The findings below are real, but they're findings about a test fixture — they tell you nothing about your production document service. If an auditor is going to look at document access, this same pass needs to run against the real code.

Using `poka-yoke:authz` (router sent me there from `poka-yoke`).

**Verdict:** you're right about `getDocument` and `Query.documents` — those two are correctly scoped. They're the only ones. Six other paths are not.

### 1. `exportWorkspace` (:52) — full cross-tenant dump, no session at all
Two failures stack. `tenantId` comes from `req.body` (client-controlled — a tenant id in a request body is an input, not an authz decision), and it's interpolated into `$queryRawUnsafe`. `tenantId = "' OR '1'='1"` returns every document and comment in the database. The function never references a session.
**Device:** take tenant from session, use tagged-template `$queryRaw` (parameterises; `queryRawUnsafe` doesn't) → **Control**. Then lint-ban `$queryRawUnsafe` repo-wide — one `where` clause fixes one site.

### 2. `adminListDocuments` (:75) — authentication mistaken for authorization
`if (!session.userId)` proves the caller is *someone*. No role check, no `tenantId` predicate: any logged-in user gets the 200 newest documents platform-wide. It accepts `session` and uses half of it, so it reads as scoped in review.
**Device:** `requireRole` + scope to `session.tenantId` → **Warning**; Control needs #7.

### 3. `updateDocument` (:41) — cross-tenant *write*
`where: { id: documentId }` with no tenant. One tenant silently rewrites another's title and body. Worse than a read: the victim has no record of the original.

### 4. `searchDocuments` (:65) — `session` declared, never used
SQL is parameterised correctly; the `tenant_id` predicate is just absent. Cross-tenant title disclosure *ranked by an attacker-chosen term* — a targeted search over every customer's data. Returned ids feed #3. A single-tenant test returns exactly the right results.

### 5. `Document.author` (:36) — `findUnique` returns the whole user row
Email, name, and every column added to `users` in future, automatically. Add an explicit `select` allowlist regardless of tenancy.

### 6. `Document.comments` / `attachments` (:29-34) — scoped by `documentId` alone
Safe today only because the one entry point is scoped — safe by coincidence, not construction. #2 and #4 already return unscoped documents; the moment either reaches the graph, these leak comment bodies.

### 7. The actual root cause
These aren't six mistakes; they're one mistake available in six places, because `db.documents` is reachable everywhere and the unscoped form is shorter. Fixing six sites leaves the affordance for the seventh. Strongest first: **RLS** (`ENABLE` *and* `FORCE ROW LEVEL SECURITY` — your app role is usually the table owner; set `app.tenant_id` per-transaction or pooling leaks it), a **scoped repository** with tenant as a required constructor arg, and the **two-tenant test** asserting 404 (not 403 — that confirms existence).

`★ Insight ─────────────────────────────────────`
Findings 2 and 4 share a tell worth internalising: both take `session` and don't use it. An unused parameter that *looks* like a scope is more dangerous than no parameter — it defeats the reviewer's glance. Worth a lint rule of its own.
`─────────────────────────────────────────────────`

**One decision before I apply anything** — #3 is the only fix with a real fork, and it's a schema call: compound unique `@@unique([id, tenantId])` reaches Control (database rejects the mismatched pair) but costs a migration; `updateMany` + `count === 0` ships today but the guard is a step a future author can omit. Which way, given your deploy window?