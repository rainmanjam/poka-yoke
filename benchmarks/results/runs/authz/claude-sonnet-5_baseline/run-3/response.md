No — it is not all scoped. Six of the eight query paths in this file leak across tenants, and three of them are live exploits with no dependency on anything else going wrong. The header comment in the fixture (`// eval fixture for tenant isolation`) confirms this file is deliberately seeded with exactly these hazards, so treat it as a template for what your real code needs to rule out, not just a one-off fix list.

**Live, directly exploitable (no chaining needed)**

1. **`exportWorkspace` (line 52-63)** — worst one. `tenantId` comes from `req.body`, not the session, and gets string-interpolated into `$queryRawUnsafe`. Any caller can pass any tenant's ID and export that tenant's full documents+comments — this is both a cross-tenant leak *and* a SQL injection (a tenantId like `' OR '1'='1` breaks out of the literal). No session check at all.
2. **`updateDocument` (line 41-50)** — `where: { id: documentId }` has no `tenantId`. `session` is accepted as a parameter and never used. Any authenticated user who knows/guesses a document ID from another tenant can overwrite its title/body.
3. **`searchDocuments` (line 65-73)** — raw SQL against `documents` with no `tenant_id` predicate. `session` is passed in and ignored. Full-text search returns titles/ids across every tenant.
4. **`adminListDocuments` (line 75-78)** — auth check is `if (!session.userId)`, i.e. "is logged in," not "is an admin of this tenant." Query has no tenant filter and no role filter — any logged-in user gets the 200 most recent documents from every tenant.

**Chained (become exploitable via #4)**

5. **`Document.comments` / `Document.attachments` resolvers (line 30-34)** — scoped only by `documentId`, no tenant check. Harmless if the parent document was fetched through the tenant-scoped `document`/`documents` query, but `adminListDocuments` hands the same `Document` type cross-tenant, so resolving `.comments`/`.attachments` on those results pulls another tenant's comment/attachment bodies.
6. **`Document.author` resolver (line 36-37)** — `db.users.findUnique({ where: { id: parent.authorId } })`, no tenant check. Chained through #4/#5, this leaks another tenant's user record (name, email) via `document.author`.

**What's actually fine:** `getDocument` (14-18) and the `document`/`documents` resolvers (22-26) are correctly scoped by `session.tenantId`. That's the "obvious path" the comment refers to — but it's 2 of 8 paths, not the whole surface.

**For the SOC2 write-up:** this maps straight to CC6.1 (logical access controls). The pattern across all six is the same root cause the authz skill calls out — nothing *forces* the tenant predicate, so it's missing wherever someone didn't think to add it by hand. The fix that actually closes this for the audit isn't patching six call sites (there will be a seventh next quarter); it's one of:
- **Postgres RLS** with `FORCE ROW LEVEL SECURITY`, tenant set per-transaction by middleware — closes it even for raw SQL and future code.
- **A scoped repository** (`DocumentRepo` constructed with a required `tenantId`) with the raw `db` client banned from handler code via lint — closes it at the type level in TS without needing RLS.

Either device, plus a two-tenant "attempt every operation from A against B's resources, assert 404" test suite, is what would actually survive an auditor asking "how do you know this doesn't happen" rather than "we reviewed the code."

Want me to implement the scoped-repository fix for this fixture, or is this purely for the audit narrative right now?