No — you're not OK. The scoping you're relying on is real, but it covers exactly the two paths people look at (`getDocument`, `Query.documents`). Everything else in the file is unscoped, and three of them are reachable by any authenticated user.

First, context that matters: this file is a benchmark fixture (`benchmarks/fixtures/`), and its own header declares it seeds hazards on purpose. It's an eval answer key, not a deployed service — so it isn't SOC2 evidence for CC6.1 either way. Auditing it as written, here's what's in it:

## Findings, worst first

**1. `exportWorkspace` (L52–63) — two critical bugs stacked.** `tenantId` comes from `req.body`, so any caller exports any tenant's documents *and* comments. There's no session read at all. And it's interpolated into `$queryRawUnsafe` — `' OR '1'='1` dumps the table regardless of tenant. The injection is a separate finding from the scoping; fixing one leaves the other.

**2. `adminListDocuments` (L75–78) — authentication mistaken for authorization.** `if (!session.userId)` proves someone is logged in. It does not check they're an admin, and it does not scope to their tenant. Any authenticated user of any customer gets the 200 most recent documents platform-wide.

**3. `searchDocuments` (L65–73) — no tenant predicate.** Accepts `session`, never uses it. Top 50 matches across every tenant. The unused parameter is what makes it read as scoped at a glance. (The `$queryRaw` tagged template *is* parameterized — no injection here, just absent scoping.)

**4. `updateDocument` (L41–50) — unscoped write.** `where: { id: documentId }` only. Tenant A can overwrite tenant B's title and body. Reads get reviewed; writes get missed.

**5. Nested resolvers `comments` / `attachments` (L29–34) — safe only by inheritance.** They filter on `parent.id` with no tenant predicate of their own. Correct today *only* because the sole path to a `Document` parent happens to be scoped. A DataLoader, a federated entity resolver, or any second parent path silently breaks it.

**6. `author` (L36–37) — unscoped `users` lookup.** `findUnique({ where: { id: parent.authorId } })` returns a user row with no tenant constraint, exposing whatever fields the schema surfaces (email, typically).

## The device

Adding `where` clauses fixes six sites and leaves the seventh available to the next person. Two structural moves:

- **Postgres RLS** on `documents`, `comments`, `attachments`, `users` with `FORCE ROW LEVEL SECURITY`, tenant set per-transaction by the only middleware that hands out connections. This is the only control that also covers scripts and migrations.
- **A scoped repository** taking `TenantId` as a required constructor arg, with the raw `db` client lint-banned from resolvers and handlers. Right now the unsafe query is the *shorter* one to write.

Then the test that proves it: two tenants, every operation from A against B's resources, assert **404 not 403** — a 403 confirms the row exists. Table-drive it off your route list so a new endpoint without a case fails rather than passes.

One decision I'd want your call on before writing the fix: on `updateDocument`, Prisma's `update` needs a unique `where`, so scoping by `{ id, tenantId }` means either a compound unique index or switching to `updateMany` and asserting `count === 1`. Which fits your schema?