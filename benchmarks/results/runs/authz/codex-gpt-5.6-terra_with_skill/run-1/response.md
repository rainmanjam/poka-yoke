# Tenant-isolation audit — `benchmarks/fixtures/documents.ts`

**Verdict:** No—scoped main queries are correct, but five other paths can expose or alter cross-tenant data unless database RLS independently blocks them.

1. **Tenant chosen from request body + SQL injection** — [documents.ts:52](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:52)

   `exportWorkspace` trusts `req.body.tenantId`, so any caller can request another tenant’s export. It also interpolates that value into `$queryRawUnsafe`, allowing the tenant predicate to be altered entirely.

   **Device:** derive tenant exclusively from authenticated session context; use parameterized queries; ideally enforce per-transaction tenant RLS. **Control** with RLS, only site-specific **Warning** otherwise.

2. **Unscoped full-text search** — [documents.ts:65](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:65)

   `searchDocuments` accepts a session but never applies `session.tenantId`. A search can return matching titles/IDs from every tenant.

   **Device:** a tenant-bound document repository (or RLS) so raw document search cannot be issued without a tenant. **Control.**

3. **“Admin” list is only authenticated, not tenant-scoped** — [documents.ts:75](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:75)

   Any signed-in user receives the latest 200 documents across all tenants. “Admin” needs an explicit global-admin authorization decision; otherwise it must filter on the session tenant.

   **Device:** separate a deliberately privileged global-admin capability from the tenant-facing repository; default tenant routes to scoped access. **Control.**

4. **Cross-tenant document modification** — [documents.ts:41](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:41)

   `updateDocument` takes a session but updates only by document ID. Someone with another document’s ID can overwrite its title/body.

   **Device:** update by `{ id, tenantId: session.tenantId }`, backed by scoped repository/RLS. The predicate alone fixes this call site; scoped access or RLS is the durable **Control**.

5. **Nested resolvers trust the parent object without rechecking tenant** — [documents.ts:29](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:29)

   `comments`, `attachments`, and `author` query solely by IDs from `parent`. With only the two shown root document queries, that parent is scoped first, so this is not a demonstrated leak today. But any future unscoped resolver—or a resolver given a constructed parent—can return related tenant data without a second tenant decision.

   **Device:** include tenant in the resolver context and constrain related rows by tenant, or use tenant-scoped repositories/RLS. **Control** with the latter.

The two primary paths are correctly constrained at [lines 14–26](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:14), but that does not protect raw SQL, update, search, admin, or associations.

One additional audit concern: the repository’s hazard detector reported “No hazards” for this deliberately hazardous fixture, so it is not evidence of tenant-isolation coverage. For SOC 2 evidence, add a table-driven two-tenant test for every operation, asserting tenant A gets a 404/no rows when targeting tenant B—while using RLS/scoped repositories as the actual prevention layer.