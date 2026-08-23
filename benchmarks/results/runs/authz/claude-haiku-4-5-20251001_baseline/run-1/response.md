## Device recommendations (strongest first)

**1. Row-level security (RLS)** — Add to your database schema. This stops *every* unscoped query in every code path, every migration, every shell script:

```sql
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON documents
  USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

Apply the same to `comments`, `attachments`, and any table that has a `tenant_id` column. Set the variable per-transaction in your connection middleware.

**2. Scoped repositories** — Make tenant a required constructor argument, so no query builder exists without one:

```ts
class DocumentRepo {
  constructor(private readonly db: Db, private readonly tenant: TenantId) {}
  
  async update(id: DocumentId, patch: object) {
    return this.db.documents.update({
      where: { id, tenantId: this.tenant },  // tenant baked in; cannot be omitted
      data: patch,
    });
  }
}
```

Ban the raw `db` client from handlers via ESLint rule.

**3. Parameterized queries everywhere** — Never build SQL from strings. Line 59's interpolation is SQL injection *and* a cross-tenant leak in one. Use `db.$queryRaw` with template literals instead.

---

**For your audit:** the exportWorkspace + searchDocuments + adminListDocuments paths are the highest-risk. `updateDocument` is also critical because writes are often less monitored than reads. Start with RLS if your database supports it — it's the only device that protects you from code paths you haven't written yet, and from future developers who won't remember these constraints. A scoped repository layer is the minimum if RLS isn't an option.