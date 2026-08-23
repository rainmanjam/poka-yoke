I've analyzed the file against the poka-yoke-authz methodology. You're right that the main query paths are scoped, but there are **4 critical tenant isolation failures** in the secondary paths — exactly the blind spots the skill warns about.

---

## SOC2 Tenant Isolation Audit — `benchmarks/fixtures/documents.ts`

`★ Insight ─────────────────────────────────────`
The file comment ("The obvious path is scoped correctly. The hazards are in the places people forget") is a pedagogical hint — this is a test fixture designed to demonstrate the authz failure pattern. Every finding below matches a category from the poka-yoke-authz audit checklist: update paths, bulk exports, search, and admin tools.
`─────────────────────────────────────────────────`

### Critical Findings

| # | Function | Line | Hazard | Impact |
|---|----------|------|--------|--------|
| **1** | `updateDocument` | 46 | `WHERE { id: documentId }` — no tenant scope on write | Any user can modify any tenant's document by ID |
| **2** | `exportWorkspace` | 53-59 | `tenantId` from `req.body`, not session | Any user can export any tenant's full workspace |
| **3** | `searchDocuments` | 65-73 | Session passed but never used; no `tenant_id` filter | Any user can search all tenants' documents |
| **4** | `adminListDocuments` | 75-78 | Checks auth but returns all tenants' documents | Any authenticated user sees 200 docs across all tenants |

### Secondary Finding

| # | Function | Line | Hazard | Impact |
|---|----------|------|--------|--------|
| **5** | Nested resolvers | 30-38 | `comments`, `attachments`, `author` trust the parent was scoped | If any path leaks a document ID (findings 2-4 do), these cascade |

---

### Details

**Finding 1 — Unscoped update (line 46)**
```ts
return db.documents.update({
  where: { id: documentId },  // missing: tenantId: session.tenantId
  data: patch,
});
```
Compare to `getDocument` at line 16 which correctly uses `{ id, tenantId: session.tenantId }`.

**Finding 2 — Client-controlled tenant + SQL injection (lines 53-59)**
```ts
const { tenantId, format } = req.body;  // tenantId from request, not session
const rows = await db.$queryRawUnsafe(
  `... WHERE d.tenant_id = '${tenantId}'`  // also: SQL injection
);
```
Two failures: tenant from client input, and string interpolation in `$queryRawUnsafe`.

**Finding 3 — Search ignores session (lines 65-73)**
```ts
export async function searchDocuments(session: Session, query: string) {
  return db.$queryRaw`
    SELECT ... FROM documents
    WHERE search_vector @@ plainto_tsquery(${query})  // no tenant_id filter
  `;
}
```
Session is accepted but never referenced. Returns matching docs from all tenants.

**Finding 4 — Admin = authenticated (lines 75-78)**
```ts
export async function adminListDocuments(session: Session) {
  if (!session.userId) throw new Error("unauthenticated");
  return db.documents.findMany({ orderBy: ..., take: 200 });  // all tenants
}
```
No role check, no tenant scope. "Admin" here means "any logged-in user."

---

### Recommendation for SOC2

This file is labeled as a **test fixture** (`benchmarks/fixtures/`), not production code. If it's only used for benchmarking your eval harness, these are intentional hazards demonstrating what the poka-yoke skill should catch.

**Action items:**
1. Confirm this file is not deployed or reachable from any production path
2. If it's imported anywhere outside `benchmarks/`, that's the real finding
3. For your actual production document service, run the same audit checklist (update paths, exports, search, admin tools, nested resolvers)

Want me to grep to confirm this file isn't imported anywhere outside of benchmarks?