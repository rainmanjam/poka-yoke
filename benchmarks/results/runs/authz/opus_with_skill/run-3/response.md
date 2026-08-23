Both the detector run and the report file write need approvals this session, so here it is in the conversation.

**First, the thing that changes your question:** `benchmarks/fixtures/documents.ts` is an eval fixture for this repo's own benchmark suite — its header says the hazards are planted deliberately, and `benchmarks/run.py` treats it as a control input. Everything below is real, but if you thought this was your production document service, it isn't. **Don't patch this file** — editing it invalidates every recorded benchmark run.

Your premise is half right. The three primary read paths *are* scoped — `getDocument:14`, `Query.document:22`, `Query.documents:25`. That's exactly why the rest is invisible. Six of nine entry points cross tenants, and three of them accept a `session` argument they never read, so the signature advertises scoping the body doesn't do.

## Findings, ranked

**1. `exportWorkspace:52` — breach / trivial.** Takes `tenantId` from `req.body` and string-interpolates it into `$queryRawUnsafe`. No `Session` parameter at all, so no login required. `{"tenantId": "' OR '1'='1"}` dumps every tenant's documents and comments in one 200. Fix: drop `tenantId` from the request schema entirely (tenant comes from session), switch to tagged-template `$queryRaw`, ban `$queryRawUnsafe` via `no-restricted-properties`. → **Control**. Then grep the whole service for `req.body.tenantId` — this is rarely the only one.

**2. `adminListDocuments:75` — breach / trivial.** `if (!session.userId)` is an authentication check standing where authorization belongs; it rejects nobody with an account. Returns 200 documents across all tenants, `createdAt` desc — competitors' *current* work. Needs `requireRole()` plus `where: { tenantId }`; "admin" means admin of a tenant. → Warning alone.

**3. `searchDocuments:65` — breach / trivial.** Parameterized (no injection) but has no tenant predicate. Ordinary use is the leak: searching "acquisition" returns the 50 most relevant matching documents across your whole customer base. It's also the **ID oracle** that arms #4 — the "they'd have to guess a UUID" defense dies here.

**4. `updateDocument:41` — corruption / easy.** No tenant predicate on a **write**. One tenant overwrites another's title and body, silently. Worst one for SOC2: disclosure *plus* integrity, no attribution. Prisma's `update` needs a unique selector, so either `updateMany({where:{id,tenantId}})` + assert `count === 1`, or add `@@unique([id, tenantId])` and use `where: { id_tenantId: {...} }` — the second makes omitting the tenant a compile error. Sweep every `update`/`delete`/`upsert` the same way; reads get reviewed, writes get missed.

**5. `Document.comments:30` / `attachments:33` — breach / latent-but-live.** Scoped by `documentId` only; safety borrowed from the parent. That borrowed safety is already spent — #2 and #3 both mint unscoped `Document` parents today.

**6. `Document.author:36` — disclosure / latent.** Unscoped `findUnique` on `users` returns the whole row. Named individuals at another customer is a different disclosure class from titles.

## Two devices that close the class

Patching six sites leaves the seventh to whoever writes it next month.

- **RLS** (`ENABLE` + `FORCE ROW LEVEL SECURITY`, policy on `current_setting('app.tenant_id')`) is the only device with reach over raw SQL — where #1 and #3 live. The catch that decides whether it's a device or theatre: set `app.tenant_id` **per transaction**, and make the middleware that sets it the only route to a connection. A pooled connection carrying the prior request's setting is a cross-tenant leak that presents as flakiness.
- **Scoped repository** — tenant as a required constructor arg, raw `db` lint-banned outside `infra/`. Promotes #2 and #3 to Control: the handler has no way to reach a client that lacks a `where`.

## The test that proves it

Two tenants; from A, attempt every operation against B's resources; assert **404, not 403** (403 confirms existence, which leaks membership). Table-drive it over the route list so a new endpoint with no case is a visible gap. Write it especially if you ship RLS — RLS failures are silent and total. And per this repo's own rule: break one scope on purpose, watch it go red, put it back. A check that has never failed is a rumour.

★ Insight ─────────────────────────────────────
The tell across #3, #4, and #5 is a `session` parameter that's accepted and never read. That's worse than no parameter at all — it makes the signature pass review while the body doesn't scope. Grepping for unused session args is a cheap Detection-rung sweep you can run before next month.
─────────────────────────────────────────────────

**Two decisions I'd want from you before writing any of this up as a plan** — both shape the remediation and neither has a single right answer: (a) RLS or scoped repo as the *primary* control — RLS covers raw SQL and code you didn't write but depends on connection hygiene; the repo is enforceable at compile time but blind to `$queryRaw`; (b) whether `updateDocument` on a cross-tenant ID returns 404 or throws, since that answer has to match `getDocument`'s null-vs-throw behaviour or the difference itself becomes an existence oracle.

I'd also like to re-run `detect_hazards.py --paths benchmarks/fixtures/documents.ts` and save the report to `docs/poka-yoke/` — both were blocked on permissions here. Say the word and I'll retry.