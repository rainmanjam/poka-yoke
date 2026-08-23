Now I have the full poka-yoke framework. Let me audit this file systematically using the authz-specific audit sequence.

---

## Tenant Isolation Audit — `benchmarks/fixtures/documents.ts`

Using **poka-yoke-authz**: the question is not "is this scoped?" but "could an unscoped query even be written here?"

---

### Finding 1: `updateDocument` — No Tenant Scope on Write (CRITICAL)

**Lines 46-47**
```ts
return db.documents.update({
  where: { id: documentId },  // ← no tenantId
  data: patch,
});
```

**Hazard**: The `session` parameter is accepted but ignored. Any authenticated user can modify any document from any tenant by knowing/guessing the ID.

**Lens**: Motion-step (M5 — check-then-act). The read path checks tenant; the write path doesn't.

**SOC2 impact**: Direct cross-tenant data modification. This is a breach, not a bug.

**Device** (Control): Add `tenantId` to the WHERE clause, or use a scoped repository that cannot construct an unscoped update.

---

### Finding 2: `exportWorkspace` — Tenant ID from Request Body (CRITICAL)

**Line 53**
```ts
const { tenantId, format } = req.body;
```

**Hazard**: The tenant is client-controlled. An attacker sets `tenantId` to any value and exports another customer's workspace.

**Lens**: Contact (C3 — primitive obsession at boundaries). The request body is trusted as the session.

**SOC2 impact**: Full data exfiltration of any tenant's documents + comments.

**Device** (Control): Pull `tenantId` from the authenticated session, never from the request.

---

### Finding 3: `exportWorkspace` — SQL Injection (CRITICAL)

**Lines 55-59**
```ts
await db.$queryRawUnsafe(
  `...WHERE d.tenant_id = '${tenantId}'`
);
```

**Hazard**: String interpolation into raw SQL. Even if Finding 2 were fixed, a malicious session value could still inject.

**Lens**: Contact (C7 — unvalidated external input).

**SOC2 impact**: Full database compromise. This bypasses all application-level controls.

**Device** (Control): Use parameterized queries (`$queryRaw` with template literals, or `$1` placeholders).

---

### Finding 4: `searchDocuments` — No Tenant Scope (CRITICAL)

**Lines 65-73**
```ts
return db.$queryRaw`
  SELECT id, title, ...
    FROM documents
   WHERE search_vector @@ plainto_tsquery(${query})
  ...
`;
```

**Hazard**: Session is passed but `tenantId` is never used. Search returns documents from all tenants.

**Lens**: Fixed-value (F3 — defaults that hide a decision). The tenant filter defaulted to "none."

**SOC2 impact**: Cross-tenant search disclosure. Titles visible = metadata leak at minimum.

**Device** (Control): Add `AND tenant_id = ${session.tenantId}` to the WHERE clause.

---

### Finding 5: `adminListDocuments` — No Tenant Scope (CRITICAL)

**Lines 75-78**
```ts
if (!session.userId) throw new Error("unauthenticated");
return db.documents.findMany({ orderBy: { createdAt: "desc" }, take: 200 });
```

**Hazard**: Checks authentication but not authorization. Returns documents from all tenants.

**Lens**: The authz skill explicitly warns: "admin usually means admin *of a tenant*; a global admin query in a tenant-facing endpoint is a leak."

**SOC2 impact**: Any authenticated user with access to this endpoint sees 200 most-recent documents across all customers.

**Device** (Control): Scope to `session.tenantId` unless this is genuinely a platform super-admin function (in which case it needs elevated privilege checks, not just `userId`).

---

### Finding 6: Nested Resolvers — No Defensive Scoping (HIGH)

**Lines 30-37**
```ts
comments: (parent: { id: string }) =>
  db.comments.findMany({ where: { documentId: parent.id } }),
attachments: (parent: { id: string }) =>
  db.attachments.findMany({ where: { documentId: parent.id } }),
author: (parent: { authorId: string }) =>
  db.users.findUnique({ where: { id: parent.authorId } }),
```

**Hazard**: These rely on the parent document being properly resolved. If any code path (batch loader, cache, direct invocation) provides a forged parent, scoping is lost. The `author` resolver could return users from other tenants if users aren't tenant-scoped.

**Lens**: Motion-step (M1 — temporal coupling). Security depends on a prior step having run.

**SOC2 impact**: Defense-in-depth failure. Not exploitable via normal GraphQL *if* all entry points are scoped, but fragile.

**Device** (Warning → Control): Either add `tenantId` to child queries defensively, or implement database RLS so the bypass is impossible regardless of code path.

---

## Summary for Your SOC2 Prep

| # | Location | Hazard | Severity | Can Tenant A See/Modify Tenant B's Data? |
|---|----------|--------|----------|-------------------------------------------|
| 1 | `updateDocument:46` | Write without tenant scope | Critical | **Yes — modify** |
| 2 | `exportWorkspace:53` | Tenant from request body | Critical | **Yes — full export** |
| 3 | `exportWorkspace:55` | SQL injection | Critical | **Yes — full database** |
| 4 | `searchDocuments:67` | Search without tenant scope | Critical | **Yes — search results** |
| 5 | `adminListDocuments:77` | Admin without tenant scope | Critical | **Yes — list 200** |
| 6 | Nested resolvers | No defensive scoping | High | Depends on other code paths |

**Your assessment that the main query paths are scoped is correct** — `getDocument` and the top-level GraphQL resolvers are fine. But 5 of the 8 exported functions bypass that scoping entirely.

---

`★ Insight ─────────────────────────────────────`
The pattern here is common: the "obvious" read path gets the tenant check, but exports, searches, updates, and admin functions are written later by someone who copied the structure without the constraint. **Scoped repositories** (where the raw `db` client is unreachable from handler code) would make all five of these unwritable.
`─────────────────────────────────────────────────`

Want me to propose specific fixes for these, or write the cross-tenant isolation test that would have caught them?