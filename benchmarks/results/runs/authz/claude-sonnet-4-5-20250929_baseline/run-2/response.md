# Security Review: Cross-Tenant Data Isolation

## Executive Summary
**Risk posture: CRITICAL** — 5 critical and 3 high-severity cross-tenant data exposure vulnerabilities found. **SOC2 compliance BLOCKED** (CC6.1 violation). Multiple paths allow customers to read and modify other tenants' data.

`★ Insight ─────────────────────────────────────`
**Nested resolvers are a common blind spot** — GraphQL resolvers that load related data (comments, attachments) often inherit the parent's authorization context but don't re-verify tenant scope. The parent document query was properly scoped, but once an attacker has a valid document ID from their tenant, the nested resolvers expose data from ANY tenant's document with that ID.

**Client-controlled tenant IDs are a critical antipattern** — Any endpoint that accepts `tenantId` from request body/query params lets attackers impersonate other tenants by simply changing a parameter.
`─────────────────────────────────────────────────`

## Findings

### 🚨 Critical (SOC2 Blockers)

**[SEC-1] Client-controlled tenant ID in export** — CVSS 10.0 — `benchmarks/fixtures/documents.ts:52-63`
- **Vulnerability**: `exportWorkspace` takes `tenantId` from `req.body`, allowing any user to export ANY tenant's data
- **Business impact**: Complete data breach capability — attacker can enumerate all tenant IDs and export every customer's documents
- **SOC2 violation**: CC6.1 (Logical Access Controls)
- **Remediation**:
```typescript
export async function exportWorkspace(req: Request, res: Response) {
  const { format } = req.body;
  const session = req.session; // Get from authenticated session
  const tenantId = session.tenantId; // NEVER from req.body
  
  const rows = await db.documents.findMany({
    where: { tenantId },
    include: { comments: true }
  });
  
  res.json({ format, rows });
}
```

**[SEC-2] SQL injection in export** — CVSS 9.8 — `benchmarks/fixtures/documents.ts:55-60`
- **Vulnerability**: String interpolation `'${tenantId}'` instead of parameterized query
- **Business impact**: Database compromise, data exfiltration
- **Remediation**: Already shown in SEC-1 fix (use ORM instead of raw SQL)

**[SEC-3] Unscoped document updates** — CVSS 9.1 — `benchmarks/fixtures/documents.ts:41-49`
- **Vulnerability**: No `tenantId` check — any user can modify any tenant's documents
- **Business impact**: Data tampering across all customers
- **SOC2 violation**: CC6.1
- **Remediation**:
```typescript
export async function updateDocument(
  session: Session,
  documentId: string,
  patch: { title?: string; body?: string },
) {
  return db.documents.update({
    where: { 
      id: documentId,
      tenantId: session.tenantId  // ← ADD THIS
    },
    data: patch,
  });
}
```

**[SEC-4] Global search across all tenants** — CVSS 8.6 — `benchmarks/fixtures/documents.ts:65-73`
- **Vulnerability**: No `WHERE tenant_id = $1` clause
- **Business impact**: Customers can search and discover other tenants' documents
- **SOC2 violation**: CC6.1
- **Remediation**:
```typescript
export async function searchDocuments(session: Session, query: string) {
  return db.$queryRaw`
    SELECT id, title, ts_rank(search_vector, plainto_tsquery(${query})) AS rank
      FROM documents
     WHERE search_vector @@ plainto_tsquery(${query})
       AND tenant_id = ${session.tenantId}  -- ← ADD THIS
     ORDER BY rank DESC
     LIMIT 50
  `;
}
```

**[SEC-5] Admin endpoint exposes all tenant data** — CVSS 8.2 — `benchmarks/fixtures/documents.ts:75-78`
- **Vulnerability**: No tenant scoping, weak auth check (only `userId` existence)
- **Business impact**: Any authenticated user can list documents across all tenants
- **SOC2 violation**: CC6.1
- **Remediation**:
```typescript
export async function adminListDocuments(session: Session) {
  // Option 1: Scope to tenant
  if (!session.userId) throw new Error("unauthenticated");
  return db.documents.findMany({ 
    where: { tenantId: session.tenantId },
    orderBy: { createdAt: "desc" }, 
    take: 200 
  });
  
  // Option 2: If truly cross-tenant admin, add role check
  if (!session.isGlobalAdmin) throw new Error("forbidden");
  return db.documents.findMany({ orderBy: { createdAt: "desc" }, take: 200 });
}
```

### ⚠️ High

**[SEC-6] Nested resolver: comments unscoped** — CVSS 7.4 — `benchmarks/fixtures/documents.ts:30-31`
- **Vulnerability**: Only filters by `documentId`, no `tenantId` check
- **Attack scenario**: Attacker queries a document they own, gets its ID structure, then crafts a GraphQL query with a guessed/leaked document ID from another tenant — the comments resolver will return that tenant's comments
- **Remediation**:
```typescript
comments: async (parent: { id: string; tenantId: string }) =>
  db.comments.findMany({ 
    where: { 
      documentId: parent.id,
      document: { tenantId: parent.tenantId }  // ← JOIN to verify
    }
  }),
```

**[SEC-7] Nested resolver: attachments unscoped** — CVSS 7.4 — `benchmarks/fixtures/documents.ts:33-34`
- Same vulnerability and fix pattern as SEC-6

**[SEC-8] Nested resolver: author unscoped** — CVSS 6.8 — `benchmarks/fixtures/documents.ts:36-37`
- **Vulnerability**: Could expose user data (email, name) from other tenants
- **Remediation**:
```typescript
author: async (parent: { authorId: string; tenantId: string }) =>
  db.users.findFirst({ 
    where: { 
      id: parent.authorId,
      tenantId: parent.tenantId  // ← ADD THIS
    }
  }),
```

## Remediation Roadmap

### Immediate (Before SOC2 Audit)
1. **SEC-1, SEC-2**: Fix `exportWorkspace` — use session tenantId, remove raw SQL (2 hours)
2. **SEC-3**: Add tenant check to `updateDocument` (15 min)
3. **SEC-4**: Add tenant filter to `searchDocuments` (15 min)
4. **SEC-5**: Scope or restrict `adminListDocuments` (30 min)

### This Week
5. **SEC-6, SEC-7, SEC-8**: Fix nested GraphQL resolvers (2 hours)
6. Add integration tests that verify cross-tenant isolation for all paths
7. Add database-level row-level security (RLS) policies as defense-in-depth

### Defense-in-Depth Recommendations
- **Database RLS**: Postgres row-level security to enforce `tenant_id` at the database layer
- **Middleware**: Add a global GraphQL middleware that validates all queries include tenant scoping
- **Monitoring**: Alert on queries returning data from multiple tenants
- **Penetration test**: Before SOC2, have auditor attempt cross-tenant access

---

**Bottom line**: You were right that the main query paths (`getDocument`, `documents`) are scoped correctly, but **5 critical paths bypass tenant isolation entirely**. The export endpoint is the most dangerous — it lets anyone export any tenant's data. This blocks SOC2 certification until fixed.