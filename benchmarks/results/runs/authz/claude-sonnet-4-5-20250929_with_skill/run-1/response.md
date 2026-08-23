★ Insight ─────────────────────────────────────
I'm following the poka-yoke-authz methodology which systematically audits for cross-tenant isolation failures. The key principle: we're not looking for "is this query scoped?" but "**could an unscoped query even be written here?**" — focusing on whether the codebase makes the unsafe form easy to write.
─────────────────────────────────────────────────

# Cross-Tenant Isolation Audit: `benchmarks/fixtures/documents.ts`

**Finding: 5 critical cross-tenant data exposure vulnerabilities**

## Critical Findings (SOC2 CC6.1 violations)

### 1. **Nested resolvers leak cross-tenant data** (lines 30-37)
**Hazard:** GraphQL resolvers for `Document.comments`, `Document.attachments`, and `Document.author` load by ID without tenant scoping.

**Attack path:**
- Attacker creates document in Tenant A
- Sets `parent.id` references to Tenant B's comment/attachment/user IDs
- Resolves nested fields to retrieve Tenant B's data

```typescript
// VULNERABLE
Document: {
  comments: (parent: { id: string }) =>
    db.comments.findMany({ where: { documentId: parent.id } }),  // no tenantId check
```

**Device:** Scoped repository pattern (Control) — require tenant on comment/attachment lookups
**Rung achieved:** Detection (tests would catch this) → needs Control

---

### 2. **Unscoped update allows cross-tenant modification** (lines 41-50)
**Hazard:** `updateDocument` checks only the document ID, not tenant ownership.

**Attack path:**
- Tenant A calls `updateDocument(sessionA, tenantB_documentId, {title: "pwned"})`
- Updates succeed — Tenant A modifies Tenant B's document

```typescript
// VULNERABLE
return db.documents.update({
  where: { id: documentId },  // missing: tenantId: session.tenantId
  data: patch,
});
```

**Device:** Add tenant to WHERE clause (Control at query level) or scoped repository (Control at type level)
**Rung achieved:** None → needs Control

---

### 3. **Client-controlled tenant ID in export** (lines 52-63)
**Hazard:** `exportWorkspace` takes `tenantId` from request body (client-controlled) + SQL injection.

**Attack path:**
- Tenant A sends `{tenantId: "tenant-b-uuid", format: "csv"}`
- Exports Tenant B's data
- SQL injection: `tenantId: "' OR 1=1 --"` exports all tenants

```typescript
// DOUBLE VULNERABILITY
const { tenantId, format } = req.body;  // client controls tenant!
// ... SQL injection via string interpolation
WHERE d.tenant_id = '${tenantId}'
```

**Device:** 
1. Use `session.tenantId` only (Control — tenant from auth, not request)
2. Parameterized query (Control — SQL injection impossible)

**Rung achieved:** None → needs Control

---

### 4. **Unscoped search returns all tenants' results** (lines 65-73)
**Hazard:** `searchDocuments` accepts `session` but never uses `session.tenantId` in the WHERE clause.

**Attack path:**
- Tenant A searches for common term
- Receives ranked results from all tenants

```typescript
// VULNERABLE — session passed but never used
SELECT id, title, ...
  FROM documents
 WHERE search_vector @@ plainto_tsquery(${query})  // no tenant_id filter
```

**Device:** Add `AND tenant_id = ${session.tenantId}` to WHERE (Control)
**Rung achieved:** None → needs Control

---

### 5. **Admin endpoint leaks all tenants** (lines 75-78)
**Hazard:** `adminListDocuments` checks authentication but not tenant scope. Returns most recent 200 documents across **all** tenants.

**Attack path:**
- Any authenticated user calls admin endpoint
- Receives cross-tenant document list

```typescript
// VULNERABLE — "admin" assumed global, not tenant-admin
return db.documents.findMany({ orderBy: { createdAt: "desc" }, take: 200 });
```

**Device:** Add `where: { tenantId: session.tenantId }` unless true global admin check exists (Control)
**Rung achieved:** None → needs Control

---

## Summary

| Finding | Line | Blast Radius | Rung | Control Device |
|---------|------|--------------|------|----------------|
| Nested resolvers | 30-37 | Read cross-tenant | Detection | Scoped repository |
| Unscoped update | 46-48 | Write cross-tenant | None | WHERE + tenantId or RLS |
| Client-controlled tenant | 53, 59 | Read all + SQLi | None | Use session.tenantId + params |
| Unscoped search | 66-71 | Read cross-tenant | None | WHERE tenant_id = session |
| Admin without scope | 77 | Read cross-tenant | None | WHERE tenantId or explicit global check |

**Recommendation:** All 5 block SOC2 certification. The good news: `getDocument` (line 14-18) shows the team knows the pattern — it's correctly scoped. The bad news: **unsafe is currently easier to write than safe** in this codebase. Every fix here is Detection-rung (caught after ship); you need a Control-rung device that makes unscoped queries unwritable — scoped repositories, RLS, or both.

Would you like me to propose specific fixes for these, or help design the Control-level device that prevents this whole class?