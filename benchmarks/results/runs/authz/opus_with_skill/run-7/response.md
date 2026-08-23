The file write wasn't approved, so here's the audit in the conversation instead (the audit skill allows either).

# Poka-Yoke Audit — `benchmarks/fixtures/documents.ts` — 2026-08-22

**Verdict:** Your premise is right and that's exactly what makes this dangerous. The three "main" paths *are* scoped — and they're the reason the other six aren't visible. **Six of the eight data-access sites in this file are unscoped.** Two return other tenants' data to any caller with no crafting required.

| Site | Line | Scoped? |
|---|---|---|
| `getDocument` | 14 | yes |
| `Query.document` | 22 | yes (delegates) |
| `Query.documents` | 25 | yes |
| `Document.comments` | 30 | **no** |
| `Document.attachments` | 33 | **no** |
| `Document.author` | 36 | **no** |
| `updateDocument` | 41 | **no** |
| `exportWorkspace` | 52 | **no** — client-supplied + injectable |
| `searchDocuments` | 65 | **no** |
| `adminListDocuments` | 75 | **no** |

---

## 1. `exportWorkspace` — client-supplied tenant + SQL injection · `:52-63`

**Mistake:** `POST` with `{"tenantId": "<any-other-tenant>"}`. This function takes no `Session` at all — nothing anywhere compares the requested tenant to the caller's. Two defects compound:

- **Client-controlled tenant.** `const { tenantId } = req.body` — the authorization subject is supplied by the party being authorized. Even with perfect SQL this is a cross-tenant export by design.
- **Injection.** `$queryRawUnsafe` with `'${tenantId}'`. Posting `{"tenantId": "' OR '1'='1"}` drops the predicate and returns every document *and comment body* in the database. It's raw SQL, so `UNION SELECT` against `users` or `sessions` is also reachable — not bounded to this table.

**Consequence:** HTTP 200, plausible payload, nothing in logs distinguishes it from a legitimate export. **Today: None.**

**Device → Control:** take the tenant from the session, switch to the parameterized tagged template.

```diff
-export async function exportWorkspace(req: Request, res: Response) {
-  const { tenantId, format } = req.body;
-  const rows = await db.$queryRawUnsafe(`... WHERE d.tenant_id = '${tenantId}'`);
+export async function exportWorkspace(session: Session, format: ExportFormat) {
+  // poka-yoke: tenant comes from the session, never the request body [control]
+  const rows = await db.$queryRaw`... WHERE d.tenant_id = ${session.tenantId}`;
```

Then ban `$queryRawUnsafe` via ESLint `no-restricted-properties` — that's what turns a one-site fix into a device.

## 2. `adminListDocuments` — authentication mistaken for authorization · `:75-78`

**Mistake:** `if (!session.userId) throw` proves *someone is logged in*. There's no role check and no `tenantId` filter. Any authenticated user from any tenant gets the 200 most recent documents platform-wide — sorted `createdAt desc`, so it returns the freshest slice from every customer.

The authz skill names this directly: "admin" almost always means admin *of a tenant*. Here it's worse — nothing establishes the caller is an admin at all.

**Device → Control:** `requireRole(session, "tenant_admin")` + `where: { tenantId: session.tenantId }`. If you need a genuinely global list for support, it belongs on a separately-authenticated internal surface with an audit-log write per call.

## 3. `updateDocument` — cross-tenant **write** · `:41-50`

**Mistake:** `where: { id: documentId }`, no tenant predicate. `session` is accepted and used for nothing. Anyone holding another tenant's document ID overwrites its title and body.

**This is the one that isn't just disclosure.** It destroys the victim's data — there's no "rotate the credential and move on." For SOC2 it hits integrity, not only confidentiality. And it **chains with #4**: search hands out other tenants' document IDs, this accepts them. No prior knowledge needed.

Note the asymmetry — the read path 27 lines above got the `tenantId` predicate and the write path didn't. Reads attract review; writes get missed.

Fix requires a schema decision — see below.

## 4. `searchDocuments` — accepts a session, never uses it · `:65-73`

The SQL *is* correctly parameterized (tagged template, no injection). But the `WHERE` clause has no `tenant_id`. Full-text search across every tenant, returning IDs and titles, ranked by relevance.

No ID-guessing needed — an attacker types a competitor's name and gets matching titles back. Titles are frequently the sensitive part.

```sql
 WHERE search_vector @@ plainto_tsquery(${query})
   AND tenant_id = ${session.tenantId}
```

Confirm your index supports the compound predicate, or the fix is correct and slow. Also: `noUnusedParameters: true` in tsconfig would have flagged this function's unused `session` at compile time — a Warning that catches precisely the "accepted a session and forgot to scope with it" shape appearing twice in this file.

## 5. `Document.comments` / `attachments` — nested resolvers inherit nothing · `:30-34`

Filter on `documentId` alone. Safe *only* while every path producing a `Document` is scoped — an invariant enforced by nothing, and already broken elsewhere in this same file. Add one unscoped document resolver and every nested field silently leaks, via a diff that never touches these lines.

Latent on the GraphQL path today, which is why it ranks below #1–#4. Scope the child query anyway; the redundancy is the point.

## 6. `Document.author` — unscoped user fetch, no field selection · `:36-37`

`findUnique` by `authorId` with no tenant predicate *and* no `select`, so the full user row reaches the GraphQL layer — email, password hash, TOTP secret, whatever's on it. Use `findFirst` (not `findUnique` — it won't take a non-unique compound `where`) with an explicit `select`.

---

## 7. The structural finding

Fixing #1–#6 fixes six sites and leaves the seventh — the one someone writes next Tuesday — exactly as available. **Six of eight sites in this file already got it wrong.** That's not six lapses; it's the interface making the mistake the default.

- **7a. Scoped repository** — tenant as a required constructor arg, then lint-ban raw `db` from handlers/resolvers so the unscoped builder isn't *reachable*.
- **7b. Postgres RLS** — the only device covering raw SQL (#1, #4), future services, migrations, and anyone with a psql shell. Two caveats decide whether it's real: set `app.tenant_id` **per transaction** (a pooled connection carrying the last request's setting is a leak with extra steps), and `FORCE ROW LEVEL SECURITY` because your app role is probably the table owner and would otherwise bypass every policy.
- **7c. Two-tenant test** — Detection rung, and the only thing that proves 7a/7b work; RLS misconfiguration fails silently and totally. Assert **404, not 403** — a 403 confirms the row exists, which leaks membership. Drive it from an enumerated operation list so a new endpoint without coverage *fails* rather than passing silently.

`★ Insight ─────────────────────────────────────`
- The three correct sites are load-bearing evidence *against* safety here: single-tenant tests pass identically whether the predicate is present or absent, so the scoped and unscoped versions are indistinguishable to your suite. That's why the two-tenant test is non-optional.
- Findings #1 and #4 are hand-written SQL. No repository abstraction and no type system would have caught either — that's the specific gap RLS exists to close, and the reason 7a alone isn't sufficient.
`─────────────────────────────────────────────────`

---

## One decision I need from you (blocks #3)

`updateDocument` can't just gain a `tenantId` in its `where` — Prisma's `update` requires a *unique* `where` input, and `{ id, tenantId }` isn't unique unless declared. This is a schema call, not a style call:

- **Option A — compound unique index.** Add `@@unique([id, tenantId])`, then `update({ where: { id_tenantId: { id, tenantId } } })`. Keeps throw-on-not-found, so a cross-tenant attempt raises. Costs a migration.
- **Option B — `updateMany`.** No migration. But it returns `{ count }` and **silently succeeds with `count: 0`** on a cross-tenant attempt — safe only if you write `if (count === 0) throw new NotFoundError()`. An unchecked count is a new silent failure replacing the old one.

**I'd take A** — it reaches Control without depending on a caller remembering to check a count, and the migration is cheap against a SOC2 finding. B is defensible if you can't take a migration before the audit, but only with the guard written at the same time.

Tell me which, and whether you want me to apply #1–#6 now — per the skill I've proposed rather than edited, since these change interface shapes (`exportWorkspace` stops being an express handler; three resolvers gain a `ctx` param) and ripple through call sites.

**Set aside:** `take: 200`/`LIMIT 50` as the only bound (resource exhaustion, not isolation); bare `string` for `userId`/`tenantId` — branded types would make `where: { id: tenantId }` a compile error, worth folding into 7a; unvalidated `format` from `req.body`, low impact but the same trust-the-body reflex that produced #1.