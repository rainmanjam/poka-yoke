## SOC2 Audit: Tenant Isolation Review

I found **6 cross-tenant exposure findings** in this file. The primary paths (lines 14–26) are correctly scoped, but the hazards are exactly where the comment warns — nested resolvers, updates, exports, and admin functions that skip the tenant check entirely.

### Findings (Severity Order)

**1. Export endpoint accepts client-controlled tenant ID + SQL injection (line 52–63)**
- *Mistake:* `tenantId` comes from `req.body` instead of `session.tenantId`; interpolated directly into SQL via `` `WHERE d.tenant_id = '${tenantId}'` ``
- *Consequence:* Any authenticated user can export any tenant's documents by specifying a different `tenantId` in the request. Combined with `$queryRawUnsafe`, this is also SQL injection.
- *Fix:* Use `session.tenantId` exclusively; parameterize the query:
  ```ts
  const rows = await db.$queryRaw`
    SELECT d.*, c.body AS comment_body
      FROM documents d
      LEFT JOIN comments c ON c.document_id = d.id
     WHERE d.tenant_id = ${session.tenantId}
  `;
  ```

**2. Update path lacks tenant scope (line 41–50)**
- *Mistake:* `updateDocument` filters by `documentId` only; no `tenantId` in the where clause.
- *Consequence:* Tenant A can modify Tenant B's documents if they know the ID.
- *Fix:* 
  ```ts
  where: { id: documentId, tenantId: session.tenantId }
  ```

**3. Nested resolvers omit tenant check (lines 30–34)**
- *Mistake:* `comments` and `attachments` resolvers load by parent ID alone. The parent document was scoped, but the child does not inherit that check.
- *Consequence:* If an attacker has a document ID, they can query `{ comments { id body } }` or `{ attachments { ... } }` and fetch any document's children from any tenant.
- *Fix:* Pass tenant context down and verify:
  ```ts
  comments: (parent: { id: string; tenantId: string }) =>
    db.comments.findMany({ 
      where: { documentId: parent.id, tenantId: parent.tenantId } 
    }),
  ```

**4. Search omits tenant scope (line 65–72)**
- *Mistake:* No `WHERE` clause filtering by `tenant_id`; returns matches across all tenants.
- *Consequence:* Tenant A can search and discover Tenant B's documents.
- *Fix:*
  ```ts
  WHERE search_vector @@ plainto_tsquery(${query})
    AND tenant_id = ${session.tenantId}
  ```

**5. Admin function lacks tenant scope and admin check (line 75–78)**
- *Mistake:* Checks for `userId` (authentication) but not for admin role; returns all documents from all tenants.
- *Consequence:* Any authenticated user can list all documents ever created by any tenant.
- *Fix:* Verify admin role **and** scope to tenant (or confirm this is intentionally a global admin function with explicit justification).

**6. Author resolver is permissive (line 36–37)**
- *Note:* Lower severity if users are not tenant-scoped, but confirm this is intentional. A user ID alone may leak membership or identity across tenants if the user record is shared.

### Devices to Add

1. **For updates/deletes:** Require tenant in the where clause at the type level:
   ```ts
   async update(id: DocId, tenantId: TenantId, patch: Patch) {
     // Constructor ensures no way to construct without tenant
   }
   ```

2. **For nested resolvers:** Add a `tenantId` field to parent objects so children can validate:
   ```ts
   interface Document {
     id: string;
     tenantId: string; // passed down so children verify
   }
   ```

3. **For all raw queries:** Use parameterized queries exclusively; ban string interpolation in SQL with a lint rule.

4. **For the session:** Add a startup check that every route except login explicitly declares its authorization policy; refuse to boot if any route is missing it.

The first two fixes are critical for SOC2. I'd recommend addressing all four in your PR before the audit.