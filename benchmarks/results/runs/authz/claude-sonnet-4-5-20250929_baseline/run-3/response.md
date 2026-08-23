Now let me analyze the code for cross-tenant data leakage vulnerabilities using a systematic approach.

★ Insight ─────────────────────────────────────
Multi-tenant security requires **defense in depth**: every query path must enforce tenant isolation, not just the primary routes. The most dangerous violations occur in:
1. **Nested resolvers** that follow references without re-checking tenant scope
2. **Client-controlled tenant IDs** accepted without validation
3. **Admin/export paths** that assume authentication = authorization
─────────────────────────────────────────────────

# Security Review: Cross-Tenant Data Leakage in documents.ts

## Executive Summary
**Risk posture: CRITICAL**. Found **5 distinct cross-tenant data exposure vulnerabilities** that violate SOC2 CC6.1 (Logical Access Controls). Any authenticated user can access data from other tenants through multiple paths. **This will block SOC2 certification.**

## Threat Model (STRIDE)

| Threat | Category | Asset | Impact | Likelihood | Risk |
|--------|----------|-------|--------|------------|------|
| User queries documents from other tenants | Information Disclosure | All documents, comments, attachments | Complete data breach across all tenants | High (easy to exploit) | **Critical** |
| User modifies other tenants' documents | Tampering | Document content | Data integrity violation, potential sabotage | High | **Critical** |
| Client specifies arbitrary tenantId | Spoofing | Workspace export data | Complete tenant impersonation | High | **Critical** |
| SQL injection in export | Injection | Database | RCE, full database dump | Medium (requires knowledge) | **Critical** |

## Findings

### Critical (CVSS 9.1) - Information Disclosure
**[SEC-1] Nested resolvers bypass tenant isolation** — `documents.ts:30-37`

The `Document.comments`, `Document.attachments`, and `Document.author` resolvers fetch related data **without scoping by tenantId**. If an attacker can reference a document ID from another tenant (via IDOR, leaked ID, or sequential guessing), these resolvers will return cross-tenant data.

```typescript
// VULNERABLE - No tenant check
Document: {
  comments: (parent: { id: string }) =>
    db.comments.findMany({ where: { documentId: parent.id } }),
```

**Business Impact:** If document IDs are predictable (auto-increment, UUID with timestamp), an attacker can enumerate and retrieve comments/attachments from all tenants.

**Remediation:**
```typescript
Document: {
  comments: async (parent: { id: string, tenantId: string }) =>
    db.comments.findMany({ 
      where: { 
        documentId: parent.id,
        document: { tenantId: parent.tenantId }  // Join to verify tenant
      } 
    }),
  
  attachments: async (parent: { id: string, tenantId: string }) =>
    db.attachments.findMany({ 
      where: { 
        documentId: parent.id,
        document: { tenantId: parent.tenantId }
      } 
    }),
  
  author: async (parent: { authorId: string, tenantId: string }) =>
    db.users.findFirst({ 
      where: { 
        id: parent.authorId,
        tenantId: parent.tenantId  // Verify user belongs to same tenant
      } 
    }),
}
```

---

### Critical (CVSS 9.3) - Tampering
**[SEC-2] Update path missing tenant isolation** — `documents.ts:41-50`

`updateDocument()` only validates the document ID exists, **not that it belongs to the session's tenant**. Any authenticated user can modify any document.

```typescript
// VULNERABLE - No tenant check in WHERE clause
export async function updateDocument(
  session: Session,
  documentId: string,
  patch: { title?: string; body?: string },
) {
  return db.documents.update({
    where: { id: documentId },  // ❌ Missing tenantId
    data: patch,
  });
}
```

**Business Impact:** Attacker can deface, corrupt, or exfiltrate data by modifying documents across all tenants.

**Remediation:**
```typescript
export async function updateDocument(
  session: Session,
  documentId: string,
  patch: { title?: string; body?: string },
) {
  const result = await db.documents.updateMany({
    where: { 
      id: documentId,
      tenantId: session.tenantId  // ✅ Enforce tenant boundary
    },
    data: patch,
  });
  
  if (result.count === 0) {
    throw new Error("Document not found or access denied");
  }
  
  return result;
}
```

---

### Critical (CVSS 10.0) - Injection + Spoofing
**[SEC-3] Client-controlled tenantId with SQL injection** — `documents.ts:52-63`

`exportWorkspace()` accepts `tenantId` from the **request body** (client-controlled) and uses it in an **unsafe string interpolation** SQL query. This has TWO critical flaws:

1. **Tenant spoofing:** Client can specify ANY tenantId to export other tenants' data
2. **SQL injection:** Unsanitized string interpolation allows arbitrary SQL execution

```typescript
// CRITICAL VULNERABILITY - Both injection and spoofing
export async function exportWorkspace(req: Request, res: Response) {
  const { tenantId, format } = req.body;  // ❌ Client controls tenantId!
  
  const rows = await db.$queryRawUnsafe(
    `SELECT d.*, c.body AS comment_body
       FROM documents d
       LEFT JOIN comments c ON c.document_id = d.id
      WHERE d.tenant_id = '${tenantId}'`,  // ❌ SQL injection
  );
```

**Business Impact:** 
- Attacker can dump entire database with payload: `tenantId: "' OR '1'='1"`
- Complete tenant impersonation by specifying victim's tenant ID
- Potential RCE via stacked queries (database-dependent)

**Remediation:**
```typescript
export async function exportWorkspace(req: Request, res: Response) {
  // ✅ Use session tenantId, not client input
  const tenantId = req.session.tenantId;
  const { format } = req.body;
  
  // ✅ Use parameterized query
  const rows = await db.$queryRaw`
    SELECT d.*, c.body AS comment_body
      FROM documents d
      LEFT JOIN comments c ON c.document_id = d.id
     WHERE d.tenant_id = ${tenantId}
  `;
  
  res.json({ format, rows });
}
```

---

### Critical (CVSS 8.6) - Information Disclosure
**[SEC-4] Search returns cross-tenant results** — `documents.ts:65-73`

Full-text search has **no tenantId filter** in the WHERE clause. Returns documents from all tenants that match the query.

```typescript
// VULNERABLE - No tenant scoping
export async function searchDocuments(session: Session, query: string) {
  return db.$queryRaw`
    SELECT id, title, ts_rank(search_vector, plainto_tsquery(${query})) AS rank
      FROM documents
     WHERE search_vector @@ plainto_tsquery(${query})  // ❌ No tenantId filter
     ORDER BY rank DESC
     LIMIT 50
  `;
}
```

**Business Impact:** Search results leak document IDs and titles across all tenants. Attacker can map the entire document corpus.

**Remediation:**
```typescript
export async function searchDocuments(session: Session, query: string) {
  return db.$queryRaw`
    SELECT id, title, ts_rank(search_vector, plainto_tsquery(${query})) AS rank
      FROM documents
     WHERE tenant_id = ${session.tenantId}  -- ✅ Scope to session tenant
       AND search_vector @@ plainto_tsquery(${query})
     ORDER BY rank DESC
     LIMIT 50
  `;
}
```

---

### Critical (CVSS 8.2) - Information Disclosure
**[SEC-5] Admin path exposes all tenant data** — `documents.ts:75-78`

`adminListDocuments()` only checks authentication (`userId` exists), but returns documents from **all tenants**. This assumes "admin = global access", but SOC2 requires tenant isolation even for admin users unless there's a documented super-admin role.

```typescript
// VULNERABLE - Authentication ≠ Authorization
export async function adminListDocuments(session: Session) {
  if (!session.userId) throw new Error("unauthenticated");
  return db.documents.findMany({ 
    orderBy: { createdAt: "desc" }, 
    take: 200 
  });  // ❌ No tenant scoping
}
```

**Business Impact:** Admin users (support staff, tenant admins) can view documents across all tenants.

**Remediation:**
```typescript
export async function adminListDocuments(session: Session) {
  if (!session.userId) throw new Error("unauthenticated");
  
  // Option 1: Scope to session tenant (tenant admin)
  return db.documents.findMany({ 
    where: { tenantId: session.tenantId },
    orderBy: { createdAt: "desc" }, 
    take: 200 
  });
  
  // Option 2: Explicit super-admin role check (if required)
  // if (!session.roles.includes('SUPER_ADMIN')) {
  //   throw new Error("Requires super-admin role");
  // }
  // Document this exception in SOC2 control narrative
}
```

---

## SOC2 CC6.1 Violations Summary

All 5 findings violate **SOC2 CC6.1: Logical Access - Segregation of Duties**:

> "The entity restricts access to information assets based on the user's role and responsibilities, and prevents users from accessing data outside their assigned scope."

**Auditor will flag:**
- ❌ Nested resolvers bypass access controls
- ❌ Update path lacks tenant authorization
- ❌ Client-controlled tenant ID in export (design flaw)
- ❌ Search and admin paths expose cross-tenant data
- ❌ No evidence of tenant isolation testing

---

## Remediation Roadmap

### Immediate (Before Audit)
1. **[SEC-3] Fix exportWorkspace SQL injection and spoofing** — Use session tenantId, parameterized queries
2. **[SEC-2] Add tenant check to updateDocument** — Prevent cross-tenant tampering
3. **[SEC-4] Scope searchDocuments by tenantId** — Add WHERE filter

### Within 48 Hours
4. **[SEC-1] Fix nested resolvers** — Add tenant joins to comments/attachments/author
5. **[SEC-5] Scope or document adminListDocuments** — Either add tenant filter OR document super-admin exception in control narrative

### Testing Required
- **Unit tests:** Verify each function rejects cross-tenant access attempts
- **Integration tests:** Confirm resolvers enforce tenant boundaries
- **Penetration test:** Attempt to access documents from Tenant B while authenticated as Tenant A

---

## Defense-in-Depth Recommendations

1. **Database-level row security:** Implement Postgres RLS policies as a failsafe:
   ```sql
   ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
   CREATE POLICY tenant_isolation ON documents
     USING (tenant_id = current_setting('app.current_tenant')::uuid);
   ```

2. **Centralized tenant scoping:** Create a helper to enforce tenant filters:
   ```typescript
   function scopeToTenant<T>(query: T, session: Session): T & { tenantId: string } {
     return { ...query, tenantId: session.tenantId };
   }
   ```

3. **Audit logging:** Log all cross-tenant access attempts for SOC2 evidence

4. **Automated testing:** Add a pre-commit hook that fails if queries lack `tenantId`

---

**Next Steps:**
1. Apply all 5 remediations immediately
2. Run regression tests to verify fixes don't break functionality
3. Schedule penetration test before SOC2 audit
4. Update control narrative to document tenant isolation controls

Would you like me to implement these fixes now, or do you need the audit report documented for your SOC2 auditor first?