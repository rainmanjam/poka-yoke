Found several critical tenant-scoping bypasses. Here's the audit:

## **CRITICAL FINDINGS**

**1. Unscoped Document Updates (Line 41–49)** — `updateDocument`
- **Mistake:** Updates are scoped only by `documentId`, not `tenantId`. Any authenticated user can modify any document in any tenant.
- **Consequence:** Cross-tenant data corruption + write IDOR.
- **Device needed:** Control. Scope the `where` clause to require both `id` AND `tenantId`:
  ```ts
  where: { id: documentId, tenantId: session.tenantId }
  ```
- **Rung:** Warning only right now (runtime validation). Should be Control via a scoped DocumentRepo that cannot be constructed without a tenant.

**2. Unscoped Search (Line 65–72)** — `searchDocuments`
- **Mistake:** Full-text search runs across ALL tenants. A user searching for "invoice" gets hits from every tenant in the database.
- **Consequence:** Information leakage + cross-tenant read IDOR.
- **Device needed:** Add `AND d.tenant_id = $1` to the query:
  ```ts
  WHERE search_vector @@ plainto_tsquery(${query}) AND tenant_id = ${session.tenantId}
  ```
- **Rung:** Warning (runtime filter). Control would be a scoped search builder that cannot omit the tenant predicate.

**3. Tenant ID from Client Body (Line 52–63)** — `exportWorkspace`
- **Mistake:** The endpoint trusts `req.body.tenantId` to control which tenant's data is exported. The client tells the server which data to leak.
- **Consequence:** Any user can export any tenant's workspace.
- **Device needed:** Control. Replace `req.body.tenantId` with `req.session.tenantId` or auth middleware that extracts it from the session, never the request body.

**4. Unscoped Admin List (Line 75–77)** — `adminListDocuments`
- **Mistake:** Lists ALL documents (all tenants) after only checking `userId` exists. No admin role check, no tenant scoping.
- **Consequence:** Any authenticated user sees every document in the system.
- **Device needed:** Control + runtime check:
  - Verify actual admin role (not just `userId`)
  - Scope to `{ where: { tenantId: session.tenantId } }` if this is "admin of a tenant," or remove the endpoint if it's meant to be global admin only (in which case use a separate auth context).

**5. Nested Resolvers Missing Tenant Checks (Lines 29–38)** — `comments`, `attachments`
- **Mistake:** These load by `documentId` alone. A user who knows document IDs from other tenants can fetch their comments/attachments.
- **Consequence:** Read IDOR via nested field resolution.
- **Device needed:** Control. Add tenant check to each:
  ```ts
  comments: async (parent: { id: string; tenantId: string }) =>
    db.comments.findMany({ 
      where: { documentId: parent.id, document: { tenantId: parent.tenantId } }
    })
  ```
- **Rung:** Depends on architecture. If `parent` carries `tenantId`, this becomes safe. If not, need to load the document first to verify tenant.

**6. SQL Injection Risk (Line 59)** — `exportWorkspace`
- **Mistake:** String interpolation of `tenantId` into raw SQL: `` `WHERE d.tenant_id = '${tenantId}'` ``
- **Consequence:** If `tenantId` is client-controlled (see #3), an attacker could inject SQL.
- **Device needed:** Control via parameterized query:
  ```ts
  `WHERE d.tenant_id = $1` with [tenantId]
  ```

---

## **SUMMARY FOR SOC2**

✅ **Primary query path** (`getDocument`, `documents` list) — correctly scoped by session tenant.

❌ **Write paths** — critically broken (updateDocument).

❌ **Non-primary paths** — all unscoped:
- Search returns all tenants' documents
- Admin list returns all tenants' documents  
- Nested resolvers (comments/attachments) can be reached across tenants
- Export trusts client-provided tenant ID

❌ **Recommendation:** Before the audit, make a two-tenant test that attempts all operations from tenant A against tenant B's resources, expecting 404 for each. This audit would catch every one of these.

Want me to propose the fixes in detail, or should you handle that internally?