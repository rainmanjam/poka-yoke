# Tenant-isolation review: `documents.ts`

## Summary

No—the scoped root queries are good, but the service is not tenant-safe overall. There are direct cross-tenant read and write paths, plus SQL injection in the export path.

## Critical

- **Client-controlled tenant + SQL injection** — [documents.ts:52](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:52)  
  `exportWorkspace` takes `tenantId` from `req.body`, so a customer can submit another tenant’s ID and receive its documents and comments. It also interpolates that value into `$queryRawUnsafe`, allowing an attacker to alter the SQL predicate and potentially export every tenant.

  Derive tenant only from an authenticated server-side session and use parameterized SQL (or the scoped repository).

## High

- **Unscoped search** — [documents.ts:65](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:65)  
  `searchDocuments` accepts a session but never uses its `tenantId`. Any search can return document IDs and titles from all tenants. The query parameter itself is safely bound; the problem is missing tenant authorization.

- **“Admin” listing is authenticated, not authorized or scoped** — [documents.ts:75](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:75)  
  Any signed-in user can retrieve the 200 newest documents across every tenant. If this is tenant admin functionality, require an explicit role and scope it to the session tenant. Global support administration should be a separately protected path.

- **Cross-tenant update / IDOR** — [documents.ts:41](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:41)  
  `updateDocument` updates by `id` alone. A user who knows another tenant’s document ID can modify it; since Prisma returns the updated row, this may also disclose its contents.

- **Nested resolvers do not independently enforce tenant ownership** — [documents.ts:29](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:29)  
  `comments` and `attachments` query only by `documentId`. They happen to be reached from currently scoped root resolvers, but that makes isolation dependent on every possible parent path remaining correct. Any future unscoped document source—or an existing one such as `adminListDocuments`—turns them into a related-data leak.

- **Unscoped author lookup** — [documents.ts:36](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:36)  
  If `users` are tenant-owned, this resolver can disclose a user from another tenant when document/user associations are inconsistent or a document crosses a boundary. Scope it too, unless authors are intentionally global and only return non-sensitive public fields.

## What is good

- [getDocument](/Users/rainmanjam/Documents/GitHub/poke_yoke/benchmarks/fixtures/documents.ts:14) and the two GraphQL root document queries correctly derive tenancy from the session.
- `searchDocuments` uses parameter binding for `query`; its issue is authorization, not SQL injection.

## Recommended control

Do not fix this only with scattered `where: { tenantId }` clauses. Make unscoped access unavailable to handlers:

1. Put all tenant-owned tables behind PostgreSQL RLS, with `FORCE ROW LEVEL SECURITY`, and set `app.tenant_id` per transaction from the authenticated session.
2. Expose a `TenantDb` / scoped repository constructed with `session.tenantId`; keep the raw client inaccessible from request handlers.
3. Require explicit server-side authorization for admin routes. Never accept `tenantId` from request input for tenant selection.
4. Use tenant-aware relationships/compound foreign keys for child records where applicable.

Add one table-driven two-tenant test: create tenants A and B, then attempt every read, search, export, nested resolver, update, and admin operation from A against B’s resources; assert no B data is returned and resource-targeted requests return `404` rather than `403`.

I also attempted the local SAST scan, but its installed Semgrep fails during CA initialization; the findings above are directly verified from the source.