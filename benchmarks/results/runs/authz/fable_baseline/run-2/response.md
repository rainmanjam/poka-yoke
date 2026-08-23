Read it. One thing first: `benchmarks/fixtures/documents.ts` is not production code. Its header says so — it's an eval fixture deliberately seeded with tenant-isolation hazards, used to grade whether the `authz` skill catches them (`benchmarks/results/runs/authz/...`). Nothing here is reachable by a customer. If your SOC2 scope is this repo, the honest answer for the auditor is "fixture, not shipped."

That said, you asked for the second pair of eyes, and the fixture is a good checklist of exactly what would leak if this pattern were in your real service. Findings, ranked:

**1. `updateDocument` — unscoped write** (`documents.ts:46-49`)
`where: { id: documentId }` with no `tenantId`. Any authenticated user who knows (or guesses) a document ID can overwrite another tenant's title/body. Writes are the path everyone forgets; reads get the attention.

**2. `exportWorkspace` — tenant ID from the request body + SQL injection** (`documents.ts:53-59`)
`tenantId` comes from `req.body`, not the session — client-controlled, so it's a one-line dump of any tenant's documents and comments. And it's string-interpolated into `$queryRawUnsafe`, so `'; DROP ...` works too. Two breaches in one function.

**3. `searchDocuments` — no tenant predicate at all** (`documents.ts:66-72`)
`session` is accepted and never used. Full-text search runs across every tenant's documents.

**4. `adminListDocuments` — "admin" is global, not per-tenant** (`documents.ts:75-78`)
Only checks the user is authenticated (not that they're an admin), then returns the 200 most recent documents across all tenants.

**5. Nested resolvers inherit nothing** (`documents.ts:29-38`)
`Document.comments` and `Document.attachments` filter by `documentId` only. That's safe *only* if the parent was always obtained through `getDocument` — but `documents` (the list) and any future resolver returning a `Document` bypass that assumption. `author` loads any user by ID, cross-tenant.

**6. `getDocument` is fine** — and that's the trap. The obvious path is scoped, which is why a spot check says "we're ok."

**Why per-site fixes aren't enough**
Every one of these is a *forgotten* check, not a wrong one. The device that holds is one where an unscoped query can't be written:
- **Postgres RLS** with `FORCE ROW LEVEL SECURITY` and `app.tenant_id` set per-transaction — catches raw SQL, exports, and scripts that no repo wrapper sees.
- A **`TenantDb` constructed only from a session**, with the raw `db` lint-banned outside infra.
- The **two-tenant test**: table-drive every operation from tenant A against tenant B's IDs, assert 404 (not 403).

**For the audit**
What I'd actually want to verify before next month is your real service, not this file: grep handlers for raw client use, every `update`/`delete` `where` clause, every `$queryRaw`, and every place `tenantId` is read from a request. Point me at that repo and I'll run the same pass.