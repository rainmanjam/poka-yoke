Found **5 tenant isolation failures** — this file would not pass a SOC2 audit as written.

`★ Insight ─────────────────────────────────────`
The main query paths ARE scoped correctly (lines 14-26). The failures are all in the places you *don't* think to look: nested resolvers, write paths, bulk exports, and full-text search.
`─────────────────────────────────────────────────`

## Critical Findings

| Line | Function | Severity | Issue |
|------|----------|----------|-------|
| 30-37 | `Document.comments/attachments/author` | **HIGH** | Nested resolvers query by `documentId` only — no tenant check. If an attacker obtains a document ID, they can fetch its comments/attachments/author regardless of tenant. |
| 41-49 | `updateDocument` | **CRITICAL** | Updates by `documentId` alone. Any authenticated user can modify any tenant's documents if they guess/obtain the ID. |
| 52-63 | `exportWorkspace` | **CRITICAL** | `tenantId` comes from `req.body`, not the session. Attacker sets `tenantId` in request → exports another tenant's data. Also SQL-injectable via string interpolation. |
| 65-73 | `searchDocuments` | **HIGH** | Full-text search has no `tenant_id` clause. Returns matches across all tenants. |
| 75-78 | `adminListDocuments` | **HIGH** | Only checks `userId` exists — no admin verification, no tenant scope. Returns all documents from all tenants. |

## Fixes Required

1. **Nested resolvers**: Pass `tenantId` through context and add `AND tenant_id = ?` to each query, or use a dataloader that filters by tenant.

2. **updateDocument**: Add `tenantId: session.tenantId` to the `where` clause (same pattern as `getDocument`).

3. **exportWorkspace**: Use `session.tenantId` (from authenticated session), not `req.body.tenantId`. Replace `$queryRawUnsafe` with parameterized query.

4. **searchDocuments**: Add `AND tenant_id = ${session.tenantId}` to the WHERE clause.

5. **adminListDocuments**: Add proper admin role check AND tenant scoping.

Want me to prepare the fixes, or do you want to address these with your team first?