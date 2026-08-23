The detector run needs an approval this non-interactive session can't grant, so what follows is a manual three-lens read of the file — which is the part the script can't do anyway. The file is 79 lines; I read all of it.

Short answer: **no, you are not OK.** The main query paths (`getDocument`, `Query.documents`) are scoped correctly, and that is exactly what makes the rest dangerous — they look like the pattern, and five other paths don't follow it. Four of them are cross-tenant leaks today; one is latent.

# Poka-Yoke Audit — `benchmarks/fixtures/documents.ts` — 2026-08-21

**Scope**: one file, 79 lines, every export and resolver.
**Verdict**: `exportWorkspace` lets any caller dump any tenant's documents and comments by putting that tenant's ID in the request body — fix that before anything else, then make the raw `db` client unreachable from this module.

## Findings

### 1. Tenant ID taken from the client — Authz bypass / trivial
**Where**: `benchmarks/fixtures/documents.ts:53-59`
**Mistake**: Send `{ "tenantId": "<someone else's>" }`. There is no session on this handler at all, so there is nothing to compare it against.
**Consequence**: Full export of another tenant's documents *joined to their comments*. Silent — returns 200 with the data. This is a reportable breach, not a bug.
**Today**: None. (Bonus: `$queryRawUnsafe` with string interpolation means `tenantId` is also a SQL injection vector — `' OR 1=1 --` exports every tenant at once.)
**Device**: Tenant comes from the session, never the body; body is parsed with a schema that has no `tenantId` field; query is parameterized. → **Control**
```ts
const { format } = ExportBody.parse(req.body);          // zod: { format: z.enum([...]) } — no tenantId exists to send
const rows = await db.$queryRaw`... WHERE d.tenant_id = ${req.session.tenantId}`;
```

### 2. Unscoped update — Authz bypass (write) / forgetting
**Where**: `documents.ts:46-49`
**Mistake**: Call `updateDocument(sessionA, idOfTenantBDoc, patch)`. Nothing stops it.
**Consequence**: Tenant A overwrites tenant B's title/body. Silent; the `session` parameter is accepted and ignored, so it *reads* as scoped.
**Today**: None.
**Device**: `where: { id, tenantId: session.tenantId }` fixes this site; the real device is #6 below, so this shape cannot be written. → **Control** via #6

### 3. Search has no tenant predicate — Authz bypass (read) / forgetting
**Where**: `documents.ts:66-72`
**Mistake**: Search for a word. Results come from every tenant's `documents`.
**Consequence**: Titles and IDs of other tenants' documents, ranked by relevance — an attacker can search for competitor names, customer names, "acquisition". Silent and plausible-looking. The IDs it leaks feed #2.
**Today**: None.
**Device**: `AND tenant_id = ${session.tenantId}` at this site; RLS (#6) makes the raw-SQL path safe even when someone forgets. → **Control** via RLS

### 4. "Admin" checks authentication, not authorization, and is global — Authz bypass / forgetting
**Where**: `documents.ts:75-78`
**Mistake**: Any logged-in user calls `adminListDocuments`. `userId` being truthy is the only check; there is no role, and no tenant.
**Consequence**: Newest 200 documents across the whole platform to anyone with an account.
**Today**: None (the `if` is a plausible-looking decoy).
**Device**: Require a `TenantAdmin` type obtained only from a role check, and scope the query. → **Control**
```ts
export async function adminListDocuments(admin: TenantAdmin) {   // only authorizeAdmin(session) can produce one
  return admin.db.documents.findMany({ orderBy: { createdAt: "desc" }, take: 200 });
}
```

### 5. Nested resolvers inherit nothing — Latent leak / one refactor away
**Where**: `documents.ts:30-37`
**Mistake**: Add any resolver that returns a `Document` parent without tenant scoping (a `documentsByIds`, a federation `__resolveReference`, a share link), or let `authorId` point at a user in another tenant after a user moves orgs.
**Consequence**: `comments`, `attachments`, and `author` are scoped only by `documentId` / `authorId`; they are safe *only because* `Query.document` happens to be scoped today. `author` already returns any user in the system by ID — `findUnique` has no tenant clause.
**Today**: Detection at best (if you have an isolation test — see #7).
**Device**: Child resolvers take the tenant from `ctx.session`, not the parent; `author` adds `tenantId`. → **Control** via #6, since a scoped repo has no unscoped `comments.findMany` to call.

### 6. The raw client is reachable from handlers — root cause of 2–5
**Where**: `documents.ts:6` (`import { db } from "./db"`)
**Mistake**: Write `db.<table>.<op>({ where: { id } })`. It is the shortest spelling, it works in every single-tenant test, and this file shows it being forgotten 4 times out of 9.
**Consequence**: Every finding above, forever, at every new call site.
**Today**: None — each site relies on the author remembering.
**Device**: a `TenantDb` constructed only from a `Session`, with the raw `db` import banned from handler/resolver directories via `no-restricted-imports`; Postgres RLS with `FORCE ROW LEVEL SECURITY` behind it so raw SQL (#1, #3) and scripts are covered too. → **Control** (the repo at the type level, RLS at the DB level — the second one catches what the first can't see).
```ts
// poka-yoke: a query with no tenant predicate cannot be written from a handler [control]
export function forSession(s: Session) { return new TenantDb(db, s.tenantId); }
```

### 7. Nothing proves any of this — Detection missing
**Device**: The two-tenant test: create A and B, run *every* export in this file as A against B's IDs, assert 404 (not 403 — 403 confirms the document exists). Table-drive it over the export list so a new function with no case fails. → **Detection**, and it is the device that tells you whether #6 actually worked.

## Set aside
- `Session.tenantId` and `documentId` are both bare `string` — `getDocument(session, tenantId)` compiles. Branded IDs would make it not compile (Control), but with #6 in place the blast radius is small.
- `exportWorkspace` has no row cap (F7) — a DoS concern, not a leak.

---

For the SOC 2 angle: findings 1–4 are CC6.1 (logical access) failures that an auditor sampling this file would find in minutes, and #7 is the evidence you'd want to hand them. I haven't changed anything — per the skill, these are proposals. If you want, I can apply #1 and #6 (the schema-parsed export and the `TenantDb` wrapper plus lint rule) and write the two-tenant test so it goes red on the current file and green after; say the word and I'll do it. I can also drop this report at `docs/poka-yoke/audit-2026-08-21.md` if you want a file for the audit binder.