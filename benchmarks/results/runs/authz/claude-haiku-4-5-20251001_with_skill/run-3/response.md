**Audit complete. I found 4 critical tenant-scoping bypasses.**

Following the authz audit sequence, here are the findings ranked by severity:

### 🔴 Critical: Cross-tenant data exposure

**1. `exportWorkspace` — tenant ID from client request body (line 52–63)**
- **Mistake:** `tenantId` comes from `req.body`, which is client-controlled. An attacker can export any tenant's documents by guessing or finding tenant IDs.
- **Consequence:** Complete read access to any tenant's data. Silent — no error, just returns the data.
- **Current device:** None.
- **Device:** Accept tenant from session, not request. Change line 53 from `const { tenantId, format } = req.body;` to `const { tenantId } = req.session;` (or similar from your session).
- **Rung:** Control (impossible to send wrong tenant once the signature changes).

**2. `searchDocuments` — unscoped full-text search (line 65–72)**
- **Mistake:** Query has no `WHERE tenant_id = ?` clause. Finds documents across all tenants.
- **Consequence:** Every document in the database is searchable from any tenant context. Silent.
- **Current device:** None.
- **Device:** Add `WHERE tenant_id = $1` and bind `session.tenantId` as the parameter.
- **Rung:** Control (SQL parameterization + required parameter).

**3. `adminListDocuments` — no tenant scope (line 75–78)**
- **Mistake:** Returns all documents from all tenants. The `userId` check is authentication, not authorization — it confirms *who* you are, not *which data* you can see.
- **Consequence:** An authenticated user from any tenant sees all documents system-wide. Silent.
- **Current device:** Only `userId` check (authentication, not authorization).
- **Device:** Add `where: { tenantId: session.tenantId }` to the findMany call.
- **Rung:** Control (scoped repository constructor pattern).

**4. `updateDocument` — unscoped update by ID (line 41–50)**
- **Mistake:** `WHERE id = documentId` only. Missing tenant check means tenant A can modify tenant B's documents.
- **Consequence:** Cross-tenant writes. Silent — the update succeeds.
- **Current device:** None.
- **Device:** Add tenant check to WHERE clause: `where: { id: documentId, tenantId: session.tenantId }`.
- **Rung:** Control (scoped repository).

### 🟡 Medium: Nested resolver scope assumption (lines 30–37)

**5. Document resolvers — inherited scope not enforced (Document.comments, Document.attachments)**
- **Mistake:** The `comments` and `attachments` resolvers load from `documentId` without verifying the parent document belongs to the requesting tenant. If a parent document from another tenant reaches this resolver, it leaks that tenant's nested data.
- **Consequence:** Cross-tenant reads *if* a document from another tenant somehow reaches a resolver. The risk depends on whether documents are ever leaked by ID (e.g., via the search or export bugs above, or through direct URL/ID sharing).
- **Current device:** None; relies on parent being scoped.
- **Device:** Each resolver should verify the parent document's tenant (or use RLS on comments/attachments tables). At minimum: `const doc = await db.documents.findFirst({ where: { id: parent.id, tenantId: session.tenantId } }); if (!doc) throw ...` before loading comments.
- **Rung:** Warning (runtime check; Control would require the session context in the resolver, which GraphQL makes awkward. See: parse-don't-validate pattern for resolvers).

---

**Bottom line for SOC2:** Issues #1–4 are immediate blockers. An auditor will flag these as design flaws, not implementation bugs. The shape of the query builder is making the unscoped query the *easy* form. Recommend moving all data access through a tenant-scoped repository layer so the unscoped query is literally impossible from a handler. That is the Control rung.

Issue #5 is lower risk if you gate #1 and #2 (the search/export that could leak cross-tenant document IDs), but it's still worth fixing to block the assumption that "parent was checked, so child is safe."