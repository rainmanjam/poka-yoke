I found **4 critical findings** in this fixture. All are exactly what the authz skill's audit sequence would catch. Here they are ranked by blast radius:

## Critical Findings

**1. exportWorkspace — Client-controlled tenant + SQL injection (lines 52–63)**
- **Mistake:** Tenant ID comes from `req.body` (line 53), not the session. Combined with string interpolation in the SQL (line 59).
- **Consequence:** Attacker requests another tenant's export via `{ tenantId: "victim-id" }`, or injects SQL to bypass the WHERE entirely. This is a complete data breach.
- **Device needed:** Control rung. Extract `tenantId` from `session` not `req.body`. Use parameterized queries to eliminate injection surface. Rung reached: Warning only (parameterization prevents injection but client control remains).

**2. updateDocument — No tenant scope on writes (lines 41–50)**
- **Mistake:** Update only checks `where: { id: documentId }`. No tenant in the WHERE clause.
- **Consequence:** Tenant A can `PATCH /documents/{any-id}` to modify Tenant B's documents. This is data corruption and breach.
- **Device needed:** Control rung. Add `tenantId: session.tenantId` to the WHERE clause, or use a scoped repository pattern so the handler never touches an unscoped query builder.

**3. searchDocuments — No tenant scope, query builder unscoped (lines 65–73)**
- **Mistake:** Raw query with no `WHERE ... tenantId = ?` filter. The `session` parameter is passed but ignored.
- **Consequence:** User can search and enumerate all documents across all tenants.
- **Device needed:** Control rung. Add `WHERE d.tenant_id = current_setting('app.tenant_id')` if using RLS, or add it to the raw query. Better: wrap in a scoped repository so this shape becomes impossible.

**4. Document.comments and Document.attachments — Nested resolvers unscoped (lines 30–34)**
- **Mistake:** These resolvers only filter by `documentId`, not tenant. They inherit authorization from the parent, but if parent loading changes, the child is exposed.
- **Consequence:** If the Document query resolver is ever misconfigured, attackers can enumerate comments/attachments from other tenants.
- **Device needed:** Warning rung (inherited from parent). Better: Control rung. Make every resolver verify tenancy independently, or enforce at the repository level so `findMany` on comments always includes a tenant check. This also catches bugs in parent scoping.

**Bonus: adminListDocuments (lines 75–78)** — Lists all documents from all tenants with only an auth check (is `userId` present), not an authz check. Either this is intentionally global-admin (in which case it should not be in this handler), or add tenant scope.

---

### What's safe
- `getDocument` (line 14) scopes correctly.
- `Query.documents` scopes correctly.
- `Query.document` delegates to `getDocument`, so it's safe.

### Device ranking for SOC2
For your audit, **Row-Level Security** in the database would reach Control rung for all of these at once — no query, from any code path, could leak cross-tenant data. That is the one device worth talking about to your auditors. Scoped repositories as a backup (Control at the type level) catches the places RLS cannot. The nested resolver issue is why you want a two-tenant test that checks every endpoint *from* tenant A *against* tenant B's resources and asserts 404.