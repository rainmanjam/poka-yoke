No worries — I have enough from reading the file directly (it's only 79 lines and the header comment literally flags where the hazards are planted). Here's the review.

**Short answer: no, you're not okay.** Only 2 of the 7 data-access paths are actually tenant-scoped. The other 5 would let one customer read or write another customer's data.

## What's fine

- `getDocument` (line 14-18) and the `Query.document` / `Query.documents` resolvers (line 20-26) — both filter by `session.tenantId`, and `tenantId` comes from the server-side session, not client input. This is the "obvious path" and it's correct.

## What's not fine

**1. `updateDocument` — cross-tenant write, no tenant check at all (line 41-50)**
```ts
return db.documents.update({
  where: { id: documentId },   // no tenantId
  data: patch,
});
```
Any authenticated user who knows or guesses a `documentId` can overwrite another tenant's document title/body. This is worse than a read leak — it's tenant A silently corrupting tenant B's data. Fix: add `tenantId: session.tenantId` to `where`, and use a compound unique constraint (`id + tenant_id`) or check the row count returned so a mismatched ID fails loudly instead of silently updating nothing (or something else).

**2. `exportWorkspace` — client-supplied tenantId + SQL injection (line 52-63)**
```ts
const { tenantId, format } = req.body;
...WHERE d.tenant_id = '${tenantId}'
```
Two separate ways to see another tenant's data: (a) `tenantId` is read straight from the request body — nothing ties it to the caller's actual session/tenant, so any authenticated (or possibly unauthenticated — there's no auth check visible in this function at all) caller can just pass a different tenant's ID and get a full document+comment export; (b) it's string-interpolated into raw SQL, so `tenantId` could also be `' OR '1'='1` to dump every tenant at once, independent of the authz bug. This is the most severe finding — it combines broken access control with injection.

**3. `searchDocuments` — no tenant filter whatsoever (line 65-73)**
Takes `session` as a parameter but never references `session.tenantId` in the query. Full-text search returns matching document titles across every tenant in the database. Easy to miss because the function signature *looks* tenant-aware (it takes a `Session`) — it just doesn't use it.

**4. `adminListDocuments` — "admin" check that isn't one (line 75-78)**
```ts
if (!session.userId) throw new Error("unauthenticated");
return db.documents.findMany({ orderBy: { createdAt: "desc" }, take: 200 });
```
This checks that the caller is *logged in*, not that they're an admin, and the query has no tenant filter. Any authenticated user from any tenant can list the 200 most recent documents platform-wide.

**5. Nested resolvers `Document.comments`, `Document.attachments`, `Document.author` — no independent tenant check (line 29-38)**
```ts
comments: (parent: { id: string }) => db.comments.findMany({ where: { documentId: parent.id } }),
attachments: (parent: { id: string }) => db.attachments.findMany({ where: { documentId: parent.id } }),
author: (parent: { authorId: string }) => db.users.findUnique({ where: { id: parent.authorId } }),
```
These trust that whatever resolved `parent` already enforced tenant scope. Today that's mostly true for the root `Query.document`/`documents` paths — but it means tenant isolation for comments/attachments/the author record depends entirely on every current *and future* resolver that produces a `Document` doing the check correctly. `updateDocument`'s bug above is a live example of a path that returns a cross-tenant `Document` with no such check; if that document is ever passed through this resolver chain (e.g., the mutation response includes nested fields), comments and attachments leak too. `author` also returns the full user row with no field selection — worth confirming it doesn't include anything like a password hash or email you don't want cross-tenant-visible.

## For your SOC2 story

This maps to CC6.1/CC6.6 (logical access — restricting access to authorized users, segregation between tenants). "Main query paths are scoped" is true but only covers 2 of 7 entry points; an auditor or pentester poking at mutations, admin routes, search, and export endpoints — which is exactly where these are — would find all five.

Want me to write this up as `docs/poka-yoke/audit-2026-08-22.md`, or go ahead and propose the actual code fixes (compound tenant+id checks, moving `exportWorkspace`'s tenantId to come from session, parameterizing the raw SQL, adding a real role check to `adminListDocuments`)?