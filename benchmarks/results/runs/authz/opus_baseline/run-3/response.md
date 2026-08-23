Two things up front. First, this file is `benchmarks/fixtures/documents.ts` — a poka-yoke eval fixture, and your message is scenario #79 verbatim in `benchmarks/scenarios.json`. Its header says the hazards are planted on purpose. So this is not a shipping code path, and nothing here is SOC2 evidence about your product. The audit below is still real — the hazards are real hazards.

Second, your premise is correct and that's the trap: `getDocument`, `Query.document`, `Query.documents` are all properly scoped. Every leak is off the main path.

## Findings, worst first

**1. `exportWorkspace` — L52-63. Full read of any tenant, unauthenticated.** Three failures stacked: `tenantId` comes from `req.body` (client-controlled), it's string-interpolated into `$queryRawUnsafe` (SQL injection — `' OR '1'='1` dumps every tenant), and `session` is never consulted. Any authenticated user, or possibly none, exports any customer's documents and comments.

**2. `updateDocument` — L41-50. Cross-tenant write.** `where: { id: documentId }` with no `tenantId`. Takes `session` and ignores it. Tenant A edits or defaces tenant B's documents. Writes get audited less than reads, which is why this one survives.

**3. `adminListDocuments` — L75-78. All tenants, no role check.** `if (!session.userId)` proves authentication, not authorization. Returns 200 documents across every tenant to any logged-in user. "Admin" here means admin *of nothing*.

**4. `searchDocuments` — L65-73. Cross-tenant search index.** Parameterized (no injection), but no tenant predicate. Returns ids and titles from every tenant — titles alone leak customer names and deal terms.

**5. Nested resolvers — L29-38.** `comments` and `attachments` scope by `documentId` only, inheriting nothing from the parent check. Safe *today* only because every parent path is scoped; findings 3 and 4 are exactly the unscoped parents that turn these into leaks. `author` (L36-37) loads any user by id with no scope at all.

## The pattern, and the device

Four of these functions accept `session` and never read it. The signature advertises a scope the body doesn't apply — a check that cannot fail, which is the failure mode this repo exists to name.

Per-site `where` clauses fix five sites and leave the sixth to whoever writes it next. The Control-rung fix is **Postgres RLS** (`ENABLE` + `FORCE ROW LEVEL SECURITY`, policy on `current_setting('app.tenant_id')`), set per-transaction by the only middleware that hands out a connection. That covers `$queryRaw` and `$queryRawUnsafe` too, which no repository wrapper does. Behind it, a scoped repo so handlers can't reach the raw client, and the two-tenant matrix test asserting **404** (not 403) for every operation A-against-B.

## One decision worth your call

`updateDocument` under RLS won't error on a cross-tenant write — it updates zero rows and returns success. In `benchmarks/fixtures/documents.ts:41`, what should 0-rows-affected do: throw a 404 (safest, hides real bugs from your own logs), throw 403 (leaks existence), or return a typed `Result` the caller must handle? That choice shapes every write path, so it should be yours, not mine.