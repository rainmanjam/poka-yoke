# Security Review: Multi-Tenant Data Isolation — documents.ts

## Executive Summary
**Risk posture: CRITICAL** — 7 cross-tenant data exposure vulnerabilities that violate SOC2 CC6.1 (Logical Access - Segregation of Duties). Any authenticated user can read, modify, or export data belonging to other tenants.

**SOC2 Impact:** These findings constitute a **Type II control failure** for data segregation. Must remediate before audit.

## Findings

### CRITICAL — Cross-Tenant Data Exposure

**[SEC-1] Unscoped document updates** — `updateDocument:41-50` — CVSS 9.1
- **Vulnerability:** Update operation missing `tenantId` constraint. Any user who discovers another tenant's `documentId` can modify their documents.
- **Attack:** `updateDocument(attackerSession, "victim-doc-123", {title: "pwned"})`
- **SOC2 CC6.1 violation:** No segregation between tenant data
- **Remediation:**
```typescript
export async function updateDocument(
  session: Session,
  documentId: string,
  patch: { title?: string; body?: string },
) {
  return db.documents.update({
    where: { id: documentId, tenantId: session.tenantId }, // Add tenantId
    data: patch,
  });
}
```

**[SEC-2] Client-controlled tenant ID in export** — `exportWorkspace:52-63` — CVSS 10.0
- **Vulnerability:** `tenantId` read from request body instead of session. Attacker can export ANY tenant's workspace.
- **Attack:** `POST /export` with `{tenantId: "victim-tenant", format: "json"}` dumps all victim data
- **Additional:** SQL injection via string interpolation on line 59
- **SOC2 CC6.1 violation:** Complete access control bypass
- **Remediation:**
```typescript
export async function exportWorkspace(req: Request, res: Response) {
  const { format } = req.body;
  const tenantId = req.session.tenantId; // Use session, not body

  const rows = await db.$queryRaw`
    SELECT d.*, c.body AS comment_body
      FROM documents d
      LEFT JOIN comments c ON c.document_id = d.id
     WHERE d.tenant_id = ${tenantId}
  `; // Use parameterized query

  res.json({ format, rows });
}
```

**[SEC-3] Global document search** — `searchDocuments:65-73` — CVSS 8.6
- **Vulnerability:** Full-text search missing `tenantId` filter. Returns ranked results across ALL tenants.
- **Attack:** Search for "confidential" and read competitors' documents
- **SOC2 CC6.1 violation:** Search index not segregated by tenant
- **Remediation:**
```typescript
export async function searchDocuments(session: Session, query: string) {
  return db.$queryRaw`
    SELECT id, title, ts_rank(search_vector, plainto_tsquery(${query})) AS rank
      FROM documents
     WHERE tenant_id = ${session.tenantId}
       AND search_vector @@ plainto_tsquery(${query})
     ORDER BY rank DESC
     LIMIT 50
  `;
}
```

**[SEC-4] Admin endpoint exposes all tenants** — `adminListDocuments:75-78` — CVSS 8.2
- **Vulnerability:** Admin function returns documents from ALL tenants. No authorization check for admin role.
- **Attack:** Any authenticated user calls this function, receives 200 most recent docs across all customers
- **SOC2 CC6.1 violation:** Admin controls don't enforce tenant boundaries
- **Remediation:**
```typescript
export async function adminListDocuments(session: Session) {
  if (!session.userId) throw new Error("unauthenticated");
  if (!session.roles?.includes('SUPER_ADMIN')) {
    // If tenant admin, scope to their tenant
    return db.documents.findMany({
      where: { tenantId: session.tenantId },
      orderBy: { createdAt: "desc" },
      take: 200
    });
  }
  // Super admins see all (log access for audit trail)
  auditLog('SUPER_ADMIN_ACCESS', session.userId);
  return db.documents.findMany({ orderBy: { createdAt: "desc" }, take: 200 });
}
```

### HIGH — Nested Resolver Data Leakage

**[SEC-5] Unscoped comments resolver** — `Document.comments:30-31` — CVSS 7.4
- **Vulnerability:** GraphQL resolver fetches comments without tenant check. If attacker guesses a `documentId`, they can read its comments even if they can't read the document itself (via error-based enumeration).
- **SOC2 CC6.1 violation:** Related data not segregated
- **Remediation:**
```typescript
comments: async (parent: { id: string; tenantId: string }) =>
  db.comments.findMany({
    where: {
      documentId: parent.id,
      tenantId: parent.tenantId // Ensure comment tenantId matches
    }
  }),
```

**[SEC-6] Unscoped attachments resolver** — `Document.attachments:33-34` — CVSS 7.4
- **Vulnerability:** Same as SEC-5 but for file attachments. Exposes S3 URLs or file metadata across tenants.
- **Remediation:**
```typescript
attachments: async (parent: { id: string; tenantId: string }) =>
  db.attachments.findMany({
    where: {
      documentId: parent.id,
      tenantId: parent.tenantId
    }
  }),
```

**[SEC-7] User info disclosure** — `Document.author:36-37` — CVSS 6.5
- **Vulnerability:** Fetches user without tenant scope. Exposes email, name, profile data of users from other tenants.
- **Business impact:** PII disclosure, GDPR Article 32 breach notification if exploited
- **Remediation:**
```typescript
author: async (parent: { authorId: string; tenantId: string }) =>
  db.users.findFirst({
    where: {
      id: parent.authorId,
      tenantId: parent.tenantId
    }
  }),
```

## SOC2 CC6.1 Remediation Roadmap

**Before audit (30 days):**

1. **Immediate (24h):**
   - Fix SEC-2 (export endpoint) — complete bypass, SQL injection
   - Fix SEC-1 (update without scope) — data tampering risk
   - Fix SEC-3 (search) — information disclosure at scale

2. **This week:**
   - Fix SEC-4 (admin endpoint)
   - Fix SEC-5, SEC-6, SEC-7 (nested resolvers)
   - Add integration test: "User from tenant A cannot access tenant B resources"

3. **Before audit:**
   - Deploy database-level Row-Level Security (RLS) policies as defense-in-depth
   - Enable query logging with tenant_id on all document reads/writes
   - Audit all other services for same patterns

4. **Compliance artifacts:**
   - Document tenant isolation architecture
   - Provide evidence of fix deployment + testing
   - Show no cross-tenant access in last 90 days of logs

## Defense-in-Depth Recommendation

Add PostgreSQL Row-Level Security as a backstop:

```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON documents
  USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

Set `app.tenant_id` from session at connection time. Even if application code fails, database rejects cross-tenant queries.

---

**Bottom line:** This code fails SOC2 CC6.1 in 7 places. All fixes are straightforward — add `tenantId` checks. Highest priority: SEC-2 (client-controlled export) is a complete breach.