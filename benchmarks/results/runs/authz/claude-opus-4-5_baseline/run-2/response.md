Found **5 cross-tenant data exposure issues** — your main query paths are fine, but the gaps are in the places auditors love to probe:

---

## Critical Findings

### 1. `exportWorkspace` (lines 52-63) — Client-controlled tenant ID
```typescript
const { tenantId, format } = req.body;  // ← attacker supplies any tenantId
```
**Impact**: Any authenticated user can export another tenant's entire workspace by passing a different `tenantId` in the request body. Also has SQL injection.

### 2. `updateDocument` (lines 41-49) — No tenant check on write
```typescript
return db.documents.update({
  where: { id: documentId },  // ← no tenantId filter
  data: patch,
});
```
**Impact**: User can modify any document by ID. Session is passed but never used.

### 3. `searchDocuments` (lines 65-73) — Unscoped full-text search
```typescript
WHERE search_vector @@ plainto_tsquery(${query})  // ← no tenant filter
```
**Impact**: Search results return documents from all tenants.

### 4. `adminListDocuments` (lines 75-78) — Auth ≠ authz
```typescript
if (!session.userId) throw new Error("unauthenticated");
return db.documents.findMany({ ... });  // ← no tenant filter, no admin role check
```
**Impact**: Any logged-in user sees all documents across all tenants.

---

## Medium Findings

### 5. Nested resolvers (lines 30-37) — Transitive exposure
```typescript
comments: (parent: { id: string }) =>
  db.comments.findMany({ where: { documentId: parent.id } }),
```
**Impact**: If a document ID leaks (logs, URLs, error messages), an attacker can query the GraphQL resolver chain to pull comments/attachments/author from another tenant's document. The root query is scoped, but children aren't — the trust boundary is at the wrong layer.

---

`★ Insight ─────────────────────────────────────`
- SOC2 CC6.1 requires logical access controls that restrict data to authorized users — these findings are direct violations
- The nested resolver pattern is a common GraphQL anti-pattern; DataLoader or resolver-level tenant guards fix it
- The "session passed but unused" smell (lines 41, 65) is a quick grep audit: `grep -n 'session.*unused\|session[^.]*$'`
`─────────────────────────────────────────────────`

---

**Bottom line**: Main reads are scoped. Writes, exports, search, and admin paths are not. These would fail a controls test. Want me to draft fixes?