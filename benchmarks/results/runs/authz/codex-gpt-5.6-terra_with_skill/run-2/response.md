# Tenant-isolation audit

**Verdict:** No—the two main read paths are scoped, but five other paths can disclose or modify cross-tenant data.

1. **Critical — export trusts a client-supplied tenant ID.** [`exportWorkspace`](</Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:52>) selects data for `req.body.tenantId`, not the authenticated session. A customer can submit another tenant’s ID. It also interpolates that value through `$queryRawUnsafe`, creating a separate SQL-injection path that could bypass the predicate entirely.  
   **Device:** derive tenant only from authenticated context and use bound SQL/ORM queries; RLS is the strongest backstop.

2. **Critical — search is entirely unscoped.** [`searchDocuments`](</Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:65>) receives a session but never uses its tenant ID, so any search returns matching documents across all tenants.

3. **High — “admin” checks authentication, not tenant authorization.** [`adminListDocuments`](</Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:75>) returns the latest 200 documents globally for any authenticated user. “Admin” must be explicitly global, or be scoped to the caller’s tenant.

4. **High — update scopes only by document ID.** [`updateDocument`](</Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:41>) accepts a session but does not use it. Anyone who obtains another document ID can modify it (and likely receive its returned data).

5. **High — nested resolvers rely on association correctness rather than enforce tenant scope.** [`comments`, `attachments`, and `author`](</Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:29>) query raw IDs without a tenant constraint. They are safe only if every parent and foreign-key relationship is permanently tenant-consistent; one bad association or alternate resolver leaks related data.

The main paths, [`getDocument`](</Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:14>) and the `documents` query, do include `session.tenantId`. That is good local protection, but it is not a system-wide control—this file demonstrates why repeating `where: { tenantId }` manually is easy to miss.

Recommended structural fix: use a tenant-scoped repository that cannot be constructed without a `TenantId`, keep the raw DB client out of request handlers, and enforce Postgres RLS on documents and related tenant-owned tables (with the tenant set per transaction). That moves this from “remember the filter” to a Control-rung boundary.

Also add a table-driven two-tenant test: for every document read, update, export, search, admin, and nested route, act as tenant A against tenant B’s resource and assert **404**. Make route enumeration automatic so a new endpoint cannot silently skip isolation coverage.

One caution: the generic detector reported zero issues here, but it does not detect missing tenant predicates; that passing result is not evidence of tenant isolation.