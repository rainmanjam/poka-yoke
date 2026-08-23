## First, the thing that changes what you do with this

`benchmarks/fixtures/documents.ts` is a **benchmark fixture with intentionally planted hazards**, not production code. Its own header says so, and it's one of only two `.ts` files in the repo — both under `benchmarks/fixtures/`, consumed by the `audit` benchmark task as the input models get graded on.

So: patching this file buys you nothing for SOC2 and would corrupt your `with_skill` vs `baseline` baseline. Your real document service isn't in this repo. What the fixture is good for is a **grep list** — it was built to encode the shapes people actually forget, and your premise ("main query paths are all scoped") is precisely the trap it's designed around. Line 3: *"The obvious path is scoped correctly. The hazards are in the places people forget."*

Findings below, ranked — read them as "go check these seven shapes in the real codebase."

## Findings

**1. `exportWorkspace` (L52–63) — full cross-tenant dump, two ways.** `tenantId` is read from `req.body`, so it's client-controlled: any authenticated user POSTs another tenant's ID and gets every document plus comment bodies. It's also string-interpolated into `$queryRawUnsafe`, so `' OR '1'='1` drops the predicate without needing to guess an ID. No session is consulted anywhere in the function.

**2. `adminListDocuments` (L75–78) — authn mistaken for authz.** `if (!session.userId)` proves someone is logged in, nothing more. No role check, no tenant filter — returns 200 most-recent documents across all tenants to any authenticated caller. `session` is otherwise unused.

**3. `searchDocuments` (L65–73) — unscoped search.** `session` is accepted and never read; no `tenant_id` predicate. The tagged template is parameterized so injection isn't the issue — the missing WHERE clause is. Search is the classic non-primary path that ships unscoped.

**4. `updateDocument` (L41–50) — unscoped write.** `where: { id: documentId }` with no tenant. Tenant A silently overwrites tenant B's title/body given an ID. Write paths get less review than reads and are destructive.

**5. Nested resolvers `comments` / `attachments` (L30–34).** Scoped by `parent.id` only. Safe *only while* every path returning a `Document` is scoped — the parent was checked, the child inherits nothing. Any future unscoped resolver turns these into leaks retroactively.

**6. `author` resolver (L36–37).** Unscoped `findUnique` returning the entire user row. Reachable via a foreign parent → leaks another tenant's user record.

**7. The `getDocument` / `documents` paths you think are safe (L14–26).** If this is Prisma, `where: { tenantId: undefined }` **drops the filter entirely** rather than matching nothing. A malformed or missing session doesn't fail closed — it returns everything. Worth confirming against your real session middleware.

## Root cause

Six of seven are the same defect: `db` is importable and unscoped, so the leaky form is the *short* form. Per-site `where` clauses fix seven sites; you have hundreds. The Control-rung fixes are Postgres RLS with `FORCE ROW LEVEL SECURITY` (set `app.tenant_id` per-transaction — pooled connections carrying a stale setting is a leak with extra steps), plus a `DocumentRepo` taking `TenantId` as a required constructor arg and lint-banning raw `db` from handlers.

For the audit itself, the artifact worth having is the two-tenant test: create A and B, run every route from A against B's resources, assert **404 not 403** (403 confirms existence), table-driven over an enumerated route list so a new endpoint without coverage fails rather than passes.

## One decision for you

`updateDocument` is the only fix with a real fork, and it's your call because it depends on your migration appetite:

- **`@@unique([id, tenantId])`** + compound `where` — enforced at the DB, but needs a migration on a large table.
- **`updateMany({ where: { id, tenantId } })`** then assert `count === 1` — no migration, but the scoping lives in code that someone can drop, and you must remember the count check.

Tell me which, and whether to sweep your actual service repo (point me at it) rather than this fixture — that's the sweep that matters before next month.