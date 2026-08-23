Read the SOC2 audit fixture and the `authz` mode of the poka-yoke skill. Your instinct on the main paths is right — `getDocument`, the `document`/`documents` resolvers all scope by `session.tenantId` correctly. But there are four paths outside that main flow where a customer could see or modify another customer's data, plus one latent gap. Here's the breakdown, worst first.

## Findings

### 1. `adminListDocuments` — returns every tenant's documents to any logged-in user
**Where**: `documents.ts:75-78`
**Mistake**: checks `session.userId` is truthy (i.e. "is someone logged in"), not that they're an admin, then queries with no `tenantId` filter at all.
**Consequence**: any authenticated user of *any* tenant gets the 200 most recent documents across the whole platform. Silent — the function name and the auth-looking check make it read as safe.
**Today**: None.
**Device** → Control:
```ts
if (!session.userId) throw new Error("unauthenticated");
return db.documents.findMany({
  where: { tenantId: session.tenantId },
  orderBy: { createdAt: "desc" }, take: 200,
});
```
Also flag separately: this checks *authenticated*, not *admin* — the name promises a role check that doesn't exist.

### 2. `exportWorkspace` — tenant ID taken from the request body, plus raw SQL injection
**Where**: `documents.ts:52-63`
**Mistake**: `const { tenantId } = req.body` — client-controlled, not from session. Interpolated directly into `$queryRawUnsafe`.
**Consequence**: anyone who can hit this endpoint can export any tenant's documents+comments by passing a different `tenantId`, and can inject SQL through it. No session/auth check present in the function at all.
**Today**: None.
**Device** → Control: take tenant from session, use a parameterized query:
```ts
export async function exportWorkspace(req: Request & { session: Session }, res: Response) {
  const { format } = req.body;
  const rows = await db.$queryRaw`
    SELECT d.*, c.body AS comment_body FROM documents d
    LEFT JOIN comments c ON c.document_id = d.id
    WHERE d.tenant_id = ${req.session.tenantId}`;
  res.json({ format, rows });
}
```

### 3. `searchDocuments` — search hits every tenant
**Where**: `documents.ts:65-73`
**Mistake**: `session` is a parameter but never used in the query — no `tenant_id` predicate.
**Consequence**: search returns matching titles from all tenants. Looks safe because `session` is right there in the signature.
**Today**: None. **Device** → Control: add `WHERE tenant_id = ${session.tenantId} AND search_vector @@ ...`.

### 4. `updateDocument` — cross-tenant write
**Where**: `documents.ts:41-50`
**Mistake**: `where: { id: documentId }` with no tenant check — one tenant can edit or corrupt another tenant's document by ID.
**Consequence**: writes get less scrutiny than reads and this is the proof — silent corruption, not just disclosure.
**Today**: None. **Device** → Control via `updateMany` + count check (Prisma's `update` needs a unique `where`, so this needs an ownership-verified path, not a compound key you don't have):
```ts
const { count } = await db.documents.updateMany({
  where: { id: documentId, tenantId: session.tenantId },
  data: patch,
});
if (count === 0) throw new NotFoundError(); // don't reveal existence
```

### Set aside
- `Document.comments`/`attachments` resolvers (`:29-34`) query by `documentId` alone with no tenant check. Not independently exploitable today — the only entry points to a `Document` (`document`, `documents`) are correctly scoped, so `parent.id` is always already yours. But it's a landmine: the moment any new path returns a `Document` unscoped (like #2 does via raw SQL), these inherit nothing. Worth scoping directly for defense in depth once the above four are fixed.
- `author` resolver (`:36-37`) returns an unfiltered `User` by ID — overexposure of fields, not cross-tenant per se, since `authorId` is expected to belong to the same tenant as the document.

**Verdict**: three read paths (`adminListDocuments`, `exportWorkspace`, `searchDocuments`) and one write path (`updateDocument`) bypass tenant scoping entirely — the "main queries are scoped" belief is true but doesn't cover admin/export/search/update, which is exactly the pattern this fixture is built to test.

Want me to write this up as `docs/poka-yoke/audit-2026-08-22.md` for your audit trail, and/or add the two-tenant isolation test (tenant A attempts every operation against tenant B's docs, asserts 404) so this class of gap fails CI instead of code review?