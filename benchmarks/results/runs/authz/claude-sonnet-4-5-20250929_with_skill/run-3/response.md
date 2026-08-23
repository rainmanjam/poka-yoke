Looking at the code, I found **5 critical cross-tenant data exposure issues** that violate SOC2 CC6.1 (logical access controls). This file appears to be an intentional test fixture (the header comment mentions "hazards"), but here's what would fail an audit:

## Critical Issues (Cross-tenant exposure)

### 1. **Nested resolvers expose cross-tenant data** (lines 30-37)
**Hazard**: GraphQL `comments`, `attachments`, and `author` resolvers have no tenant scoping.

```ts
Document: {
  comments: (parent: { id: string }) =>
    db.comments.findMany({ where: { documentId: parent.id } }),  // ❌ no tenantId
  
  attachments: (parent: { id: string }) =>
    db.attachments.findMany({ where: { documentId: parent.id } }),  // ❌ no tenantId
  
  author: (parent: { authorId: string }) =>
    db.users.findUnique({ where: { id: parent.authorId } }),  // ❌ cross-tenant user lookup
}
```

**Impact**: When tenant A queries their document, the nested fields load comments/attachments/authors from ALL tenants who happen to share those IDs. The parent check doesn't propagate.

**Device needed**: Scoped repository (Control) — pass `session.tenantId` through context to nested resolvers.

---

### 2. **Unscoped write operation** (lines 46-49)
**Hazard**: `updateDocument` writes without tenant check.

```ts
return db.documents.update({
  where: { id: documentId },  // ❌ no tenantId in WHERE
  data: patch,
});
```

**Impact**: Tenant A can modify tenant B's documents. This is a **write vulnerability** — worse than a read leak.

**Device needed**: Add `tenantId: session.tenantId` to the `where` clause (Warning-level fix), or use scoped repository pattern (Control).

---

### 3. **Client-controlled tenant scope** (lines 52-63) — **MOST SEVERE**
**Hazard**: `exportWorkspace` takes `tenantId` from request body, not session.

```ts
const { tenantId, format } = req.body;  // ❌ CLIENT-CONTROLLED

const rows = await db.$queryRawUnsafe(
  `WHERE d.tenant_id = '${tenantId}'`,  // ❌ uses client value + SQL injection
);
```

**Impact**: Any user can export ANY tenant's data by changing `req.body.tenantId`. Also has SQL injection via string interpolation.

**Device needed**: Use `session.tenantId` instead (Control), and switch to parameterized query to fix injection.

---

### 4. **Unscoped search** (lines 65-73)
**Hazard**: `searchDocuments` searches across all tenants.

```ts
SELECT ... FROM documents
 WHERE search_vector @@ plainto_tsquery(${query})  // ❌ no tenant filter
```

**Impact**: Search results leak cross-tenant. A user searching "invoice" sees matches from every tenant's documents.

**Device needed**: Add `AND tenant_id = ${session.tenantId}` to the WHERE clause.

---

### 5. **Admin without tenant scope** (lines 75-78)
**Hazard**: `adminListDocuments` returns documents from all tenants.

```ts
return db.documents.findMany({ orderBy: { createdAt: "desc" }, take: 200 });
  // ❌ no WHERE clause at all
```

**Impact**: "Admin" likely means admin *of a tenant*, but this returns 200 docs from the entire database. If any endpoint calls this, it's a full data leak.

**Device needed**: Add `where: { tenantId: session.tenantId }` unless this truly is a global super-admin function (rare).

---

## SOC2 CC6.1 Violation Summary

All 5 issues violate **CC6.1** (logical access controls) because they allow users to access data outside their authorized scope. Issues #2 and #3 also enable **modification** of other tenants' data.

## Recommended Control-level Device

The cleanest fix: **scoped repository pattern** (from poka-yoke-authz). Make it impossible to construct a query without tenant scope:

```ts
class DocumentRepo {
  constructor(private readonly db: Db, private readonly tenant: TenantId) {}
  
  async byId(id: string) {
    return this.db.documents.findFirst({ 
      where: { id, tenantId: this.tenant }  // tenant baked in
    });
  }
}
```

Then ban raw `db.*` access from handlers via lint rule. The unsafe form becomes greppable and rare.

---

**For the audit**: You said "the main query paths are all scoped" — that's true (lines 14-26 are correct), but the **non-primary paths failed**: nested resolvers, writes, exports, search, and admin. That's exactly where the poka-yoke skill said to look.