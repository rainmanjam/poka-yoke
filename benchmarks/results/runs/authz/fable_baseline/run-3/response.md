One thing up front: `benchmarks/fixtures/documents.ts` is the eval fixture for this repo's authz benchmark — its header comment literally says the hazards are planted. If this is a stand-in for your real service, great; if an auditor would be looking at the real code, run this same review there. Either way, here is what's in the file, and it is not OK. The "main query paths are scoped" claim is true — and that's exactly the pattern: `getDocument` and `Query.documents` are fine, everything off the happy path leaks.

## Findings, ranked

**1. `exportWorkspace` — tenant id from the request body, plus SQL injection** (`benchmarks/fixtures/documents.ts:53-59`)
`tenantId` comes from `req.body`, not the session. Any authenticated user can POST another tenant's id and receive every document *and every comment* for that tenant. The id is also string-interpolated into `$queryRawUnsafe`, so `' OR 1=1 --` dumps the whole table. This one is a breach on its own.

**2. `updateDocument` — unscoped write** (`:46-49`)
`where: { id: documentId }` has no `tenantId`. Tenant A can overwrite the title/body of any document whose id it knows. Writes get missed because reads get the attention; this is the textbook case.

**3. `searchDocuments` — no tenant predicate at all** (`:66-72`)
`session` is accepted and never used. Full-text search runs across every tenant's documents and returns ids and titles. Parameterised, so no injection, but a cross-tenant read of titles is still disclosure.

**4. `adminListDocuments` — "admin" means global** (`:75-78`)
The only check is "has a userId". Returns the 200 most recent documents across all tenants to any logged-in caller. There's no role check and no tenant scope.

**5. Nested resolvers inherit nothing** (`:29-38`)
`Document.comments`, `attachments`, and `author` are scoped by `parent.id` only. The parent is checked at `Query.document`, so in isolation these are safe — but the moment any other resolver or mutation returns a `Document` shape (including a leaked one via #3 or #4), the children are free. `author` loads a user by id with no tenant filter at all.

## Why a line-by-line fix isn't the answer

Adding `tenantId: session.tenantId` to #2 and #3 fixes two sites. The actual defect is that **`db` — the unscoped client — is reachable from every handler**, so the unscoped query is the short, easy thing to write. The devices that reach Control:

- **Postgres RLS** on `documents`, `comments`, `attachments`, `users` with `FORCE ROW LEVEL SECURITY` and `app.tenant_id` set per-transaction from the session. This also catches `$queryRawUnsafe` and anything else that bypasses the ORM.
- **A `TenantDb` built from the session** (constructor requires `tenantId`), with the raw `db` lint-banned from handler/resolver files. Then `updateDocument`/`searchDocuments` can't be written unscoped.
- **Delete `exportWorkspace`'s body-sourced tenant** — scope from session only. `tenant_id` in a request body is client-controlled, full stop.
- **The two-tenant test**: create tenants A and B, call every exported function from A against B's ids, assert 404/empty. For SOC2 this is also the evidence artifact — it shows the control is tested, not just asserted.

If you'd like, I can write the `TenantDb` wrapper and the two-tenant test against this fixture so you have a concrete before/after to show the auditor.