Found **4 tenant isolation violations** that would fail SOC2. Your main query paths are fine — the problems are in the places the comment at the top warns about.

| Line | Function | Issue |
|------|----------|-------|
| 30-34 | `Document.comments/attachments/author` | Nested resolvers fetch by `documentId` only — no tenant check. If a GraphQL query returns a document, the nested data comes back regardless of which tenant owns it. |
| 41-49 | `updateDocument` | WHERE uses only `id: documentId`. Any authenticated user can update any document if they guess/enumerate IDs. |
| 52-63 | `exportWorkspace` | `tenantId` comes from `req.body`, not session. Attacker supplies their own `tenantId` → exports another tenant's data. Also SQL injection via string interpolation. |
| 65-73 | `searchDocuments` | Full-text search has no tenant filter. Returns matching docs from **all** tenants. |
| 75-78 | `adminListDocuments` | Checks only `userId` exists (auth), not tenant scope or admin role. Lists all tenants' docs. |

`★ Insight ─────────────────────────────────────`
The nested resolver pattern is the sneakiest — the root query is scoped, but child resolvers trust the parent blindly. GraphQL dataloaders often bypass the tenant check you put at the top level.
`─────────────────────────────────────────────────`

**Fixes needed:**

1. **Nested resolvers**: Pass `ctx.session.tenantId` through and add a WHERE clause, or validate the parent's tenantId matches session before fetching children.
2. **updateDocument**: Add `tenantId: session.tenantId` to the WHERE clause.
3. **exportWorkspace**: Use `session.tenantId` instead of `req.body.tenantId`, and use parameterized queries.
4. **searchDocuments**: Add `AND tenant_id = ${session.tenantId}` to the WHERE clause.
5. **adminListDocuments**: Add tenant scope + actual admin role check.

Want me to write the fixed versions?