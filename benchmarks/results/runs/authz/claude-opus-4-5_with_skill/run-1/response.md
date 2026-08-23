## SOC2 Tenant Isolation Audit — `benchmarks/fixtures/documents.ts`

You're right that the main query paths (`getDocument`, `Query.document`, `Query.documents`) are correctly scoped. But the authz skill warns specifically about the paths people forget: **updates, exports, search, admin, and nested resolvers**. This file has issues in all of them.

---

### Critical Findings (Block Ship)

| # | Location | Hazard | Impact |
|---|----------|--------|--------|
| **1** | `updateDocument` :41-50 | No tenant scope on UPDATE — `where: { id: documentId }` ignores session entirely | Tenant A can overwrite Tenant B's documents |
| **2** | `exportWorkspace` :52-63 | `tenantId` taken from `req.body`, not session; also SQL injection via `$queryRawUnsafe` | Attacker exports any tenant's workspace by supplying their ID |
| **3** | `searchDocuments` :65-73 | No `tenant_id` filter in WHERE clause | Search returns documents from all tenants |
| **4** | `adminListDocuments` :75-78 | Only checks authentication, returns all documents across all tenants | Any authenticated user sees every tenant's documents |

---

### High Findings (Nested Resolvers)

| # | Location | Hazard | Impact |
|---|----------|--------|--------|
| **5** | `Document.comments` :30-31 | Nested resolver queries by `documentId` only, no tenant scope | Comments leak if document ID is known |
| **6** | `Document.attachments` :33-34 | Same pattern as comments | Attachments leak if document ID is known |
| **7** | `Document.author` :36-37 | Returns user by ID without tenant check | Leaks user data across tenants |

---

### Why These Slip Through

The authz skill calls out this exact pattern:

> "Cross-tenant data leaks are almost never caused by a wrong access-control decision. They are caused by *no decision at all*."

The `getDocument` function shows someone knew to scope by tenant. But that discipline didn't reach the secondary paths — and in a SOC2 audit, these are exactly what gets tested.

---

### Recommended Devices (Strongest First)

1. **Database RLS** (Control) — Postgres row-level security on all tenant-scoped tables, with `app.tenant_id` set per-transaction. Only fix that holds regardless of code path.

2. **Scoped Repository** (Control) — Replace raw `db` access with a `TenantRepo` class that takes `tenantId` in its constructor. Lint-ban `db.` from handler code.

3. **Isolation Test Suite** (Detection) — Create two tenants, attempt every operation from tenant A against tenant B's resources, assert 404 (not 403) for all.

---

### Immediate Actions for SOC2

1. **Fix `updateDocument`** — add `tenantId: session.tenantId` to the where clause
2. **Fix `exportWorkspace`** — use `session.tenantId`, switch to parameterized query
3. **Fix `searchDocuments`** — add `AND tenant_id = ${session.tenantId}` 
4. **Fix `adminListDocuments`** — scope to session tenant, or add explicit superadmin role check
5. **Fix nested resolvers** — pass `ctx.session` through and add tenant scopes

Want me to propose the specific code changes for each fix?