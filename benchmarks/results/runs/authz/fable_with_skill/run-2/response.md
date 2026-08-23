I have enough to answer. Short version first: **no, you are not ok.** The two obvious paths (`getDocument`, `Query.documents`) are scoped correctly, and that's exactly why this file is dangerous — everything *else* in it leaks. Five of the eight code paths let tenant A reach tenant B's data, and two of them let A *modify* or *dump* it.

Ranked by blast radius. "Today" is what currently stops the mistake; "Device" is the fix and the rung it reaches (Control = impossible, Warning = fails loudly, Detection = found later).

## Findings

### 1. Export takes `tenantId` from the request body — Breach / Trivial
**Where**: `benchmarks/fixtures/documents.ts:53-59`
**Mistake**: Any authenticated caller POSTs `{ "tenantId": "<someone else's>" }`.
**Consequence**: Full dump of another tenant's documents *and comments*. Silent — it's a 200. Also `$queryRawUnsafe` with string interpolation, so `tenantId = "' OR 1=1 --"` dumps **every** tenant at once. This alone fails SOC 2 CC6.1.
**Today**: None.
**Device**: Tenant comes from the session only; use the tagged-template `$queryRaw` so interpolation is impossible → **Control**
```ts
const { format } = req.body;
const rows = await db.$queryRaw`SELECT ... WHERE d.tenant_id = ${req.session.tenantId}`;
```

### 2. `updateDocument` is unscoped — Breach (write) / Trivial
**Where**: `documents.ts:46-49`
**Mistake**: Caller passes any document ID.
**Consequence**: Tenant A overwrites tenant B's title/body. Prisma's `update` on a unique `where` can't take `tenantId`, which is why people drop it — the API nudges you into the bug.
**Today**: None (the `session` parameter is accepted and never read — a "fixed-value" miss).
**Device**: `updateMany({ where: { id, tenantId: session.tenantId } })` and treat `count === 0` as 404, or a composite unique on `(id, tenantId)` → **Control** at this site.

### 3. Nested resolvers inherit nothing — Leak / Easy
**Where**: `documents.ts:30-37` (`comments`, `attachments`, `author`)
**Mistake**: Child resolvers filter by `parent.id` only, trusting that the parent was scoped.
**Consequence**: Any other resolver or future field that returns a `Document` shape (search is one — see #4) hands over another tenant's comments and attachments. `author` looks up users globally, so a cross-tenant document leaks author PII.
**Today**: Implicit trust in the parent.
**Device**: Add `tenantId: ctx.session.tenantId` to every child query (Warning-ish, per-site) — or better, a `TenantRepo` constructed with the session's tenant so there is no unscoped `db` reachable from resolvers → **Control**.

### 4. `searchDocuments` has no tenant predicate — Leak / Trivial
**Where**: `documents.ts:66-72`
**Mistake**: Searching returns top-50 matches across *all* tenants.
**Consequence**: Cross-tenant titles and IDs — and those IDs then feed #3's nested resolvers. The `session` argument is unused.
**Today**: None.
**Device**: `AND tenant_id = ${session.tenantId}` in the query → **Control** at this site.

### 5. `adminListDocuments` is global, gated only on "logged in" — Leak / Trivial
**Where**: `documents.ts:75-78`
**Mistake**: Checks `userId` exists, not that the user is an admin, and not of which tenant.
**Consequence**: Every authenticated user gets the 200 most recent documents across the whole platform.
**Today**: None — the `if` looks like a check but checks the wrong thing.
**Device**: Role check *and* `where: { tenantId: session.tenantId }`; "admin" means admin-of-a-tenant → **Control**.

## The device that fixes all five at once

Each fix above is one site. The reason five slipped through is that the raw `db` client is importable from handler code, so the unscoped query is the *short* form. Two devices reach Control for the whole file, not just these lines:

1. **Postgres RLS** on `documents`, `comments`, `attachments` with `FORCE ROW LEVEL SECURITY` and `app.tenant_id` set per-transaction by middleware. This is the only thing that also protects scripts, migrations, and the next handler nobody's reviewed yet.
2. **The two-tenant test** (`Detection`, but it's the auditor's favourite evidence): create tenants A and B, run every exported function as A against B's IDs, assert 404/empty. Table-drive it over the export list so a new function without a case fails CI.

## Set aside
- `format` in export is echoed back unvalidated (low; not a tenancy issue).
- `session.userId` truthiness check in #5 would pass `"0"`-style junk; moot once #5 is fixed.

Per the skill I'm proposing, not editing. This is a benchmark fixture (the header comment says the hazards are planted), so if what you actually want is this analysis run against your real service, point me at it and I'll do the same pass there — and I'd write the two-tenant test first, since that's the artifact that goes in the SOC 2 evidence folder.