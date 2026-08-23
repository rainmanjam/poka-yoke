Confirmed — this file is not "mostly ok, just double-check it," it's leaking across tenants in **three separate places**, one of them severely. Here's the audit, ranked by blast radius.

**Scope**: `benchmarks/fixtures/documents.ts`, 79 lines.
**Verdict**: `searchDocuments` and `adminListDocuments` return other tenants' data to any authenticated user with zero tenant filtering — these are the ones to fix before anything else.

## Findings

### 1. `searchDocuments` has no tenant filter at all — Critical/Trivial
**Where**: `documents.ts:65-73`
**Mistake**: Any authenticated user searches for a common term.
**Consequence**: The raw SQL has no `WHERE tenant_id = ...` clause — it searches and returns `id`/`title` across **every tenant's documents**. `session` is accepted as a parameter and never referenced. Silent: results look like a normal search response.
**Today**: None.
**Device (Control)**:
```ts
export async function searchDocuments(session: Session, query: string) {
  return db.$queryRaw`
    SELECT id, title, ts_rank(search_vector, plainto_tsquery(${query})) AS rank
      FROM documents
     WHERE tenant_id = ${session.tenantId}
       AND search_vector @@ plainto_tsquery(${query})
     ORDER BY rank DESC
     LIMIT 50
  `;
}
```

### 2. `adminListDocuments` is a fake auth check over an unscoped query — Critical/Trivial
**Where**: `documents.ts:75-78`
**Mistake**: Any logged-in user (not an admin — just anyone with a truthy `userId`) calls this.
**Consequence**: `if (!session.userId)` only checks "is someone logged in," not "is this an admin," and even for a real admin it should mean *admin of their own tenant*. The query has no tenant filter — it returns the 200 most recent documents **across every tenant**.
**Today**: None (the `if` reads like a check but authorizes nothing meaningful).
**Device (Control)**: require an actual admin-role check, and scope to the admin's own tenant:
```ts
export async function adminListDocuments(session: Session) {
  if (!session.isAdmin) throw new Error("forbidden");
  return db.documents.findMany({
    where: { tenantId: session.tenantId },
    orderBy: { createdAt: "desc" },
    take: 200,
  });
}
```

### 3. `exportWorkspace` trusts a client-supplied `tenantId`, plus SQL injection — Critical/Trivial
**Where**: `documents.ts:52-63`
**Mistake**: The function signature takes `req`/`res` directly rather than a `Session`, and reads `tenantId` from `req.body` — a value the caller fully controls. Any authenticated user can export tenant B's data by putting `tenantId: "<other-tenant>"` in the request body.
**Consequence**: Full document + comment export for any tenant, on request. Compounding: the raw SQL is built with string interpolation (`'${tenantId}'`), so it's also SQL-injectable — an attacker doesn't even need a valid tenant ID, they can inject `' OR '1'='1` and get everything, or worse.
**Today**: None.
**Device (Control)**: take `tenantId` from the session, never the body, and use parameterized SQL:
```ts
export async function exportWorkspace(session: Session, req: Request, res: Response) {
  const { format } = req.body;
  const rows = await db.$queryRaw`
    SELECT d.*, c.body AS comment_body
      FROM documents d
      LEFT JOIN comments c ON c.document_id = d.id
     WHERE d.tenant_id = ${session.tenantId}`;
  res.json({ format, rows });
}
```

### 4. `updateDocument` writes by ID with no tenant check — High/Easy
**Where**: `documents.ts:41-50`
**Mistake**: Any tenant's session can call `updateDocument(session, otherTenantsDocId, patch)` — the `where` clause is `{ id: documentId }` only.
**Consequence**: Silent cross-tenant write — tenant A can overwrite tenant B's document title/body. Worse than a read leak because it's data corruption, not just exposure.
**Today**: None.
**Device (Control)**: scope the `where`, and check the row was actually matched (Prisma's `update` throws on zero matches, which is itself a useful signal — don't swallow that error into a generic 500 that could tell an attacker whether the ID exists in another tenant; return 404 either way).
```ts
return db.documents.update({
  where: { id: documentId, tenantId: session.tenantId },
  data: patch,
});
```
Note: this requires a compound unique constraint on `(id, tenantId)` — Prisma's `update.where` only accepts unique/id fields, so this is a schema change, not just an app-code one.

### 5. `Document.comments` / `Document.attachments` resolvers inherit no scope — Medium/Latent
**Where**: `documents.ts:29-34`
**Mistake**: These nested resolvers filter only by `documentId: parent.id`, with no independent tenant check. Today they're only reachable through `getDocument`, which *is* scoped, so this isn't currently exploitable — but it's exactly the blind spot the authz skill calls out: "the parent was checked and the child inherits nothing." Any future resolver, batched loader, or GraphQL federation path that hands these a `Document` object without going through `getDocument` reopens it instantly, silently.
**Today**: None (works only by accident of the current call graph).
**Device (Control)**: pass tenant context down and check it explicitly rather than relying on the parent:
```ts
comments: (parent: { id: string; tenantId: string }, _: unknown, ctx: { session: Session }) =>
  db.comments.findMany({ where: { documentId: parent.id, document: { tenantId: ctx.session.tenantId } } }),
```

### 6. `Document.author` resolver has no tenant check on the returned user — Low/Latent
**Where**: `documents.ts:36-37`
**Mistake**: `db.users.findUnique({ where: { id: parent.authorId } })` returns a full `User` record with no tenant scoping. Currently benign for the same reason as #5 — `authorId` only comes from an already-scoped document — but it means the author lookup would happily return a user from a *different* tenant if `authorId` were ever wrong or the schema allowed cross-tenant authorship.
**Today**: None, relies on upstream invariants holding forever.
**Device (Warning, not Control — this one's cheap insurance, not the priority)**: assert `user.tenantId === parent.tenantId` and throw rather than return silently if it doesn't match.

## Set aside
- `getDocument` and the `Query.document` / `Query.documents` resolvers (lines 14-27) — these are correctly scoped by `session.tenantId`. That's your "obvious path," per the file's own comment.

For SOC2 CC6.1 (logical access controls), #1-#4 are the ones an auditor would flag as reportable — they're not edge cases, they're the direct query path with the tenant check either absent or spoofable. #5-#6 matter for defense-in-depth but aren't independently exploitable today.

Want me to:
1. Write this out to `docs/poka-yoke/audit-2026-08-22.md` as an audit-trail artifact, and/or
2. Apply the fixes (I'd start with #1-#3, then confirm the schema change needed for #4 before touching it)?

I'd also recommend the two-tenant test pattern from the `authz` skill — create tenant A and B, run every exported function/resolver from A against B's document ID, assert 404 across the board. That's what would have caught all four of the critical findings automatically, and it's the thing that stops a fix here from regressing later.