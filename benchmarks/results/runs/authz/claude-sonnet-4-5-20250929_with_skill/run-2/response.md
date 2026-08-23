Reviewing `benchmarks/fixtures/documents.ts` for cross-tenant data exposure ahead of your SOC2 audit.

★ Insight ─────────────────────────────────────
This fixture demonstrates the exact failure patterns that cause real SOC2 findings: missing tenant scopes in nested resolvers, client-controlled tenant IDs, and admin paths that forget tenant boundaries. Each one violates CC6.1 (logical access controls).
─────────────────────────────────────────────────

# Poka-Yoke Authz Audit — documents.ts — 2026-08-20

**Scope**: `benchmarks/fixtures/documents.ts` — 79 lines, 6 functions, GraphQL resolvers  
**Verdict**: **Five cross-tenant exposure paths violating SOC2 CC6.1** — nested resolvers leak by association, update/search/admin paths unscoped, export accepts client-controlled tenant_id

---

## Critical Findings

### 1. Nested resolvers leak across tenants — Critical/Easy
**Where**: `documents.ts:30-37` (Document.comments, Document.attachments, Document.author)  
**Mistake**: Craft a GraphQL query referencing a known document ID from another tenant; the parent document check passes (scoped correctly), but nested fields load by ID association without re-checking tenant_id  
**Consequence**: **Silent cross-tenant data leak**. Comments, attachments, and user records from other tenants returned in the same query. No error, no audit trail.  
**Today**: None  
**Device**: Scoped nested resolvers that inherit session context → **Control**

```ts
Document: {
  comments: (parent: { id: string, tenantId: string }, _: unknown, ctx: { session: Session }) =>
    db.comments.findMany({ 
      where: { documentId: parent.id, tenantId: ctx.session.tenantId } 
    }),
  
  attachments: (parent: { id: string, tenantId: string }, _: unknown, ctx: { session: Session }) =>
    db.attachments.findMany({ 
      where: { documentId: parent.id, tenantId: ctx.session.tenantId } 
    }),
  
  author: (parent: { authorId: string, tenantId: string }, _: unknown, ctx: { session: Session }) =>
    db.users.findUnique({ 
      where: { id: parent.authorId, tenantId: ctx.session.tenantId } 
    }),
}
```

Control-rung alternative: Database RLS policies on comments/attachments/users tables enforce tenant_id in the query layer; impossible to bypass even if resolver forgets.

---

### 2. Unscoped update allows cross-tenant modification — Critical/Easy
**Where**: `documents.ts:46-48`  
**Mistake**: Call `updateDocument(session, otherTenantDocId, {title: "pwned"})`  
**Consequence**: **Silent cross-tenant write**. One tenant modifies another's document. Returns success. No 404, no audit event.  
**Today**: None  
**Device**: Add `tenantId` to WHERE clause → **Control**

```ts
return db.documents.update({
  where: { id: documentId, tenantId: session.tenantId },  // ← add tenant check
  data: patch,
});
```

Control-rung alternative: Scoped repository pattern (DocumentRepo requires tenant in constructor; raw db access lint-banned from handlers).

---

### 3. Client-controlled tenant_id in export — Critical/Trivial
**Where**: `documents.ts:52-63`  
**Mistake**: POST `{tenantId: "victim-tenant-uuid", format: "json"}` from attacker session  
**Consequence**: **Complete tenant data exfiltration**. Attacker exports any tenant's full workspace. Also: SQL injection via string template (line 59).  
**Today**: None  
**Device**: Use session.tenantId, never req.body.tenantId; parameterized query → **Control**

```ts
export async function exportWorkspace(req: Request, res: Response) {
  const { format } = req.body;
  const { session } = req;  // assume middleware sets this
  
  const rows = await db.$queryRaw`
    SELECT d.*, c.body AS comment_body
      FROM documents d
      LEFT JOIN comments c ON c.document_id = d.id
     WHERE d.tenant_id = ${session.tenantId}`;  // ← from session, not body; parameterized
  
  res.json({ format, rows });
}
```

**This is the highest-severity finding** — requires zero reconnaissance, trivial to exploit, exfiltrates complete dataset.

---

### 4. Search unscoped, returns all tenants' documents — Critical/Easy
**Where**: `documents.ts:65-72`  
**Mistake**: Call `searchDocuments(session, "quarterly report")`  
**Consequence**: **Silent cross-tenant search results**. Returns top 50 matches across ALL tenants' documents. Leaks document IDs, titles, and existence of search terms in competitors' data.  
**Today**: None  
**Device**: Add tenant_id filter to WHERE clause → **Control**

```ts
return db.$queryRaw`
  SELECT id, title, ts_rank(search_vector, plainto_tsquery(${query})) AS rank
    FROM documents
   WHERE tenant_id = ${session.tenantId}  -- ← add tenant scope
     AND search_vector @@ plainto_tsquery(${query})
   ORDER BY rank DESC
   LIMIT 50`;
```

---

### 5. Admin path ignores tenant, returns global dataset — Critical/Easy
**Where**: `documents.ts:75-78`  
**Mistake**: Assume "admin" means "can see everything"; most SaaS admin is *per-tenant admin*, not global  
**Consequence**: **Every authenticated user sees all tenants' documents** (200 most recent). No privilege escalation needed — any valid session works.  
**Today**: Detection (authentication check only)  
**Device**: Scope to session.tenantId unless explicitly global admin → **Control**

```ts
export async function adminListDocuments(session: Session) {
  if (!session.userId) throw new Error("unauthenticated");
  
  // If this is genuinely global admin, require explicit flag:
  const where = session.isGlobalAdmin 
    ? {}  // unscoped, but greppable and rare
    : { tenantId: session.tenantId };  // default: tenant-scoped admin
  
  return db.documents.findMany({ where, orderBy: { createdAt: "desc" }, take: 200 });
}
```

Control-rung alternative: Separate `adminListDocuments` (tenant-scoped, default) and `globalAdminListAllDocuments` (unscoped, explicit, lint-flagged).

---

## SOC2 Impact

All five findings map to **CC6.1** (logical access controls — "the entity implements logical access security software to restrict access"). Auditors will sample API endpoints and trace request → query → returned rows; any path that returns another tenant's data is a control deficiency. 

The client-controlled tenant_id (finding #3) is also a **CC7.2** violation (system monitoring — injection attacks should be detected/prevented).

---

## Recommended Order of Remediation

1. **exportWorkspace** (finding #3) — highest severity, trivial exploit, also has SQL injection
2. **searchDocuments** (finding #4) — global search is high-volume, likely to leak in normal use
3. **updateDocument** (finding #2) — write path, silent corruption
4. **adminListDocuments** (finding #5) — likely called frequently, high exposure
5. **Nested resolvers** (finding #1) — requires GraphQL knowledge, but still critical

---

## The Test That Proves It

```ts
describe("tenant isolation", () => {
  it("denies cross-tenant access on all endpoints", async () => {
    const tenantA = await createTenant();
    const tenantB = await createTenant();
    const docB = await createDocument(tenantB);
    
    const routes = [
      () => getDocument(tenantA.session, docB.id),           // expect null
      () => updateDocument(tenantA.session, docB.id, {}),    // expect error/null
      () => searchDocuments(tenantA.session, docB.title),    // expect docB NOT in results
      () => adminListDocuments(tenantA.session),             // expect docB NOT in results
    ];
    
    for (const call of routes) {
      const result = await call();
      expect(result).not.toContainDocument(docB);  // assert 404, not 403
    }
  });
});
```

Assert **404, not 403** — a 403 confirms the resource exists, leaking membership. 404 is indistinguishable from "never existed."

---

**Ready to fix these, or do you want the findings written to `docs/poka-yoke/` first?** The export endpoint (finding #3) should be patched immediately if this is production code.