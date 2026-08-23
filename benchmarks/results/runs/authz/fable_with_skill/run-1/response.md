Short answer: **no, you're not ok.** The two primary paths (`getDocument`, `Query.documents`) are scoped correctly, and that's exactly the problem — they're the paths that get looked at. Six of the nine operations in this file are unscoped. Ranked by blast radius:

### 1. Tenant ID taken from the request body — Authz bypass / Silent, trivially reachable
**Where**: `benchmarks/fixtures/documents.ts:53-59`
**Mistake**: `exportWorkspace` reads `tenantId` from `req.body`, not the session. Any authenticated user posts `{"tenantId": "<victim>"}` and gets the victim's entire workspace — documents *and* comments — as JSON.
**Also**: `$queryRawUnsafe` with string interpolation is SQL injection; `tenantId: "' OR 1=1 --"` dumps every tenant at once.
**Today**: None.
**Device**: Take the tenant from the session and only the session; use the tagged-template `$queryRaw` so interpolation is parameterized → **Control**. Then lint-ban `$queryRawUnsafe` outside `infra/`.

### 2. Unscoped update — Cross-tenant write / Requires only forgetting
**Where**: `documents.ts:46-49`
**Mistake**: `updateDocument` takes a `session` and never uses it. `where: { id }` lets tenant A overwrite any document whose ID they know or guess.
**Today**: None (the unused parameter makes it *look* scoped).
**Device**: `where: { id: documentId, tenantId: session.tenantId }` fixes this site. Control for the *class* is a scoped repo (see below).

### 3. Global admin query in a tenant-facing path — Read leak
**Where**: `documents.ts:75-78`
**Mistake**: `adminListDocuments` checks *authenticated*, not *admin*, and then lists the latest 200 documents across every tenant.
**Today**: None.
**Device**: Scope to `session.tenantId` plus a real role check on the session.

### 4. Search is unscoped — Read leak / Silent
**Where**: `documents.ts:66-72`
**Mistake**: Full-text search has no `tenant_id` predicate. Any user can enumerate other tenants' titles by searching common words.
**Today**: None. (`$queryRaw` tagged template is at least injection-safe.)
**Device**: `AND tenant_id = ${session.tenantId}`.

### 5. Nested resolvers inherit nothing — Read leak via association
**Where**: `documents.ts:29-38`
**Mistake**: `Document.comments` / `attachments` / `author` filter only by `parent.id`. Today the parent is scoped, so these are safe *by accident* — the moment anyone adds a resolver that returns a `Document` from an unscoped path (search above returns `id` already), the children leak. `author` also resolves any user by ID.
**Today**: Detection at best (depends on every parent resolver staying correct).
**Device**: Filter children by `tenantId: ctx.session.tenantId` too, or stop passing raw `db` to resolvers.

### The device for the whole class

Every finding above is the same mistake: `db` is reachable from handler code, so the unscoped query is the *short* form. Control for all of them at once:

```ts
class TenantDb {
  constructor(private db: Db, private tenant: TenantId) {}   // no default — cannot exist unscoped
  documents = { byId: (id) => this.db.documents.findFirst({ where: { id, tenantId: this.tenant } }), ... }
}
```

Build one per request in middleware, lint-ban `import { db }` outside `infra/`, and add the two-tenant test (every op from A against B's IDs → **404**). If Postgres: `ENABLE` + `FORCE ROW LEVEL SECURITY` on `documents`/`comments`/`attachments` catches the paths nobody has written yet.

### For the SOC2 conversation
This file's own header comment says it's an eval fixture with *planted* hazards — if it's a benchmark and not production code, none of this is a finding against your real system. But the pattern it illustrates (primary paths scoped, secondary paths forgotten) is the one to audit for in your actual service: grep for raw `db.` / `$queryRaw` in handlers, and check update, export, search, admin, and nested resolvers specifically.

I proposed, didn't edit. Say the word and I'll apply the scoped-repo shape and the two-tenant test.