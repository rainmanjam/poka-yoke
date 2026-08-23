Before the findings — one thing that changes what you do with them:

**This file is not production code.** It's a benchmark eval fixture. Its own header says so (`benchmarks/fixtures/documents.ts:1-4`), it imports a `./db` that doesn't exist, and it's referenced only by grading runs under `benchmarks/results/runs/authz/` and `poka-yoke-workspace/iteration-2/authz-tenant-isolation/`. The hazards in it were **planted on purpose** to test whether a model finds them. It's also the only TypeScript in this repo apart from `payments.ts`, which is the other fixture — so if you're prepping SOC2 evidence, none of the actual system is in this repo. Worth confirming you're pointed at the right tree.

That said, here's the review. The findings are real as code, and they're a good checklist for the real one.

## Findings, worst first

**1. `exportWorkspace` (:52-63) — client supplies the tenant.** `const { tenantId } = req.body`, interpolated into raw SQL. No session is read at all. Any authenticated caller dumps any tenant's documents *and* comments by editing one JSON field. It's also SQL injection — `'` in `tenantId` and the `WHERE` clause is yours. Two breaches in nine lines.

**2. `adminListDocuments` (:75-78) — authentication mistaken for authorization.** `if (!session.userId)` proves someone is logged in, nothing more. No role check, no tenant filter. Returns the 200 newest documents across every tenant to any logged-in user.

**3. `updateDocument` (:41-50) — unscoped write.** `where: { id: documentId }` with no `tenantId`. Cross-tenant *modification*, which is worse than a read: it's silent, and it corrupts the other tenant's data rather than just exposing it. This is the one your instinct about "main query paths" misses — reads get scoped, writes get forgotten.

**4. `searchDocuments` (:65-73) — takes `session`, never uses it.** Full-text search over the whole `documents` table. The unused parameter is the tell: it looks scoped at the call site. (The `$queryRaw` tag is parameterized, so no injection here — just total isolation failure.)

**5. Nested resolvers (:29-38) — inherit nothing.** `comments`, `attachments`, and `author` scope only by the parent's id. That's *transitively* safe when the parent came from `Query.document`, which is scoped — but findings 2 and 4 hand these resolvers unscoped parents. `author` is the worst: `findUnique` with no field selection returns the whole user row, so a leaked document leaks the author's PII too.

`★ Insight ─────────────────────────────────────`
Your premise — "the main query paths are all scoped" — is correct, and that's precisely why the file leaks. `getDocument` and `Query.documents` are both textbook. Every hazard is on a path nobody thinks of as a query path: an export, a search, an update, a GraphQL field. Auditing "are the queries scoped?" finds nothing here.

The corollary: adding `tenantId` to these five sites fixes five sites. Postgres RLS with `FORCE ROW LEVEL SECURITY` fixes the class, including the code paths you haven't written yet.
`─────────────────────────────────────────────────`

Want me to point this same review at your actual application repo? That's the one the auditor will ask about.