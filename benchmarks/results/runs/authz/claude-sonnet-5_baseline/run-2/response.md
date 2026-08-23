I read through the file directly (didn't just trust the prior session's memory). You're **not** fully okay — the two main read paths are scoped correctly, but there are five spots where tenant scoping is missing or bypassable. For a SOC2 CC6.1 (logical access control) audit, these are the kind of findings that matter most since they're cross-tenant exposure.

**1. `updateDocument` — cross-tenant write (Critical)**
`documents.ts:41-50` — `where: { id: documentId }` has no `tenantId`. Any authenticated user who knows/guesses a `documentId` from *any* tenant can overwrite its title/body. This is worse than a read leak — it's tenant A silently corrupting tenant B's data.

**2. `exportWorkspace` — tenant ID trusted from request body + SQL injection (Critical)**
`documents.ts:52-63` — `tenantId` comes from `req.body`, not the session, so a caller can export *any* tenant's documents and comments by just passing a different ID. Compounding it, the query is built with raw string interpolation (`` `WHERE d.tenant_id = '${tenantId}'` ``) via `$queryRawUnsafe` — that's a SQL injection on top of the authz bug, so the tenant filter itself can't be trusted even if it were sourced from the session.

**3. `searchDocuments` — no tenant filter at all (Critical)**
`documents.ts:65-73` — takes `session` as a parameter but never references `session.tenantId` in the query. Full-text search returns matches across every tenant's documents.

**4. `adminListDocuments` — auth check that isn't (High)**
`documents.ts:75-78` — checks `session.userId` is truthy, which just means "logged in," not "admin." It also has no tenant scoping, so it returns the 200 most recent documents system-wide to any authenticated user.

**5. `Document.comments` / `Document.attachments` / `Document.author` resolvers — nested resolvers trust the parent (Medium, but real given #4 exists)**
`documents.ts:29-38` — these fetch by `parent.id`/`parent.authorId` with no tenant check of their own. That's fine *only if* every path that produces a `Document` was itself tenant-scoped — which is false today because of #4. Once `adminListDocuments` can hand back a cross-tenant document, these nested fields leak that document's comments, attachments, and author record too. Nested resolvers inheriting nothing from the parent's scope is a classic blind spot.

**What's actually fine:** `getDocument` and the `documents` query resolver (`documents.ts:14-27`) correctly scope by `session.tenantId`.

**Recommended devices** (per the audit skill, ranked by durability):
- Row-level security on `documents`/`comments`/`attachments` (`FORCE ROW LEVEL SECURITY`, keyed on a per-transaction `app.tenant_id` setting) — the one control that holds even when a handler forgets.
- A scoped repository (`tenant` required in the constructor) so an unscoped Prisma/SQL client isn't reachable from handler code at all.
- Kill `$queryRawUnsafe` with string interpolation — use parameterized queries everywhere, which also closes the injection.
- A cross-tenant regression test: two tenants, every operation from A against B's IDs, assert 404 (not 403 — 403 confirms existence).

Want me to write the fixes (scoped repo + RLS migration + the two-tenant test), or do you just need this write-up for the audit evidence file?