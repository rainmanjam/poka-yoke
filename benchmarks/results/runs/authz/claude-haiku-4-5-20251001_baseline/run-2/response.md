Found 4 critical tenant-scoping bypasses. Here's what I'm seeing:

**1. `updateDocument` — missing tenant scope entirely**
```ts
// Line 41-50: checks documentId but not tenantId
return db.documents.update({
  where: { id: documentId },  // ← any document can be updated
  data: patch,
});
```
**Risk:** Customer A can modify any document by guessing/knowing the ID, even if it belongs to Customer B.

**Fix:** Add `tenantId` to the where clause:
```ts
where: { id: documentId, tenantId: session.tenantId }
```

---

**2. `exportWorkspace` — tenant ID from client + SQL injection**
```ts
// Line 52-63: takes tenantId from req.body, not from session
const { tenantId, format } = req.body;
// ... then interpolates into raw SQL
WHERE d.tenant_id = '${tenantId}'  // ← both auth bypass and SQL injection
```
**Risk:** Customer A can export Customer B's entire workspace by passing a different `tenantId` in the request body. Plus SQL injection via the `tenantId` parameter.

**Fix:** Use the tenant from session, and parameterize:
```ts
const rows = await db.$queryRaw`
  SELECT d.*, c.body AS comment_body
    FROM documents d
    LEFT JOIN comments c ON c.document_id = d.id
   WHERE d.tenant_id = ${session.tenantId}
`;
```

---

**3. `searchDocuments` — no tenant filter at all**
```ts
// Line 65-73: searches ALL documents in system, ignores tenantId
SELECT id, title, ts_rank(...)
  FROM documents
 WHERE search_vector @@ plainto_tsquery(${query})
 // ← missing: AND tenant_id = ${session.tenantId}
```
**Risk:** Customer A's search queries return results from all other customers' documents.

**Fix:** Add tenant filter to WHERE clause.

---

**4. `adminListDocuments` — no permission check**
```ts
// Line 75-78: only checks if userId exists, not if admin
if (!session.userId) throw new Error("unauthenticated");
return db.documents.findMany({ orderBy: { createdAt: "desc" }, take: 200 });
// ← returns 200 docs from ALL tenants
```
**Risk:** Any authenticated user can call this and get 200 arbitrary documents. "Admin" is not verified.

**Fix:** Add actual admin check (probably needs a role/permissions lookup):
```ts
if (!session.userId) throw new Error("unauthenticated");
const user = await db.users.findUnique({ where: { id: session.userId } });
if (user?.role !== "admin") throw new Error("forbidden");
// ... now return tenant-scoped results anyway
return db.documents.findMany({ 
  where: { tenantId: session.tenantId },
  orderBy: { createdAt: "desc" }, 
  take: 200 
});
```

---

**5. Nested resolvers — bypasses document scoping**
```ts
// Lines 30-31: if someone gets a document object, they can fetch comments
comments: (parent: { id: string }) =>
  db.comments.findMany({ where: { documentId: parent.id } }),  // doesn't check tenant
```
**Risk:** If GraphQL execution reaches a document from another tenant (via the bypasses above), nested fields like `comments` and `attachments` will leak. The `author` resolver could also leak user info across tenants.

**Fix:** Pass tenant context through or add scoping at resolver level:
```ts
comments: (parent: { id: string, tenantId: string }) =>
  db.comments.findMany({ where: { documentId: parent.id, tenantId: parent.tenantId } })
```

---

**For SOC2 audit:** I'd recommend:
- Add Row-Level Security (RLS) at the database level as a defense-in-depth layer
- Create a scoped repository pattern that all queries go through
- Add integration tests with two tenants to catch these bypasses (query as tenant A, verify no tenant B data leaks)

These are all fixable but they're the kinds of bugs that slip in because the "obvious path" (`getDocument`) is scoped correctly, so people think everything is.