One caveat up front: this file is a **benchmark fixture**, not production code — the header comment says it's a deliberately seeded eval case for the repo's own authz detector. So it won't show up in your SOC2 scope, but the findings are still a good illustration of what to look for in the real service. Ranked:

## Findings

**1. `exportWorkspace` — tenant ID taken from the client, plus SQL injection** (`documents.ts:52-63`)
`tenantId` comes from `req.body`, not the session. Any authenticated user posts `{"tenantId": "<victim>"}` and gets every document *and comment* in that workspace. Worse, it's interpolated into `$queryRawUnsafe`, so `tenantId: "' OR 1=1 --"` dumps **all tenants** in one request. This is the full-blast-radius one.

**2. `updateDocument` — no tenant in the `where`** (`:46-49`)
`update({ where: { id } })` lets tenant A overwrite the title/body of any document whose ID they know. Write paths get missed because reads get all the review attention.

**3. `searchDocuments` — no tenant predicate at all** (`:65-73`)
The session is passed in but never used. Full-text search returns matches across every tenant; a search for a competitor's name is a cross-tenant leak.

**4. `adminListDocuments` — "admin" is global, not tenant-admin** (`:75-78`)
The only check is "has a userId". Returns the 200 newest documents across all tenants to any logged-in user.

**5. Nested resolvers inherit nothing** (`:29-38`)
`Document.comments/attachments/author` trust `parent.id`. Today that's fine because `Query.document` is scoped — but if any other resolver ever returns a `Document` (search, export, a future "shared" feature), the children go unscoped with it. `author` also looks up a user with no tenant check, so a cross-tenant `authorId` yields another customer's user record.

**What's fine:** `getDocument` and `Query.documents` (`:14-26`).

## The device, not the fix

Patching these five sites fixes five sites. The point of this fixture is that the scoped `getDocument` looked fine and the other 80% of the file didn't — the unsafe form was the *short* form. For your real service, before the audit:

- **Row-level security** on `documents`/`comments`/`attachments` with `FORCE ROW LEVEL SECURITY`, `app.tenant_id` set per-transaction by the only middleware that hands out connections. This is the one control that covers scripts, migrations, and the path nobody wrote yet.
- **Two-tenant isolation test**: table-driven over your route list, tenant A hits every endpoint with tenant B's IDs, asserts **404** (not 403 — 403 confirms existence). An endpoint without a row fails the test.
- Lint-ban `$queryRawUnsafe` and the raw client from handler code.

If you'd like, point me at the actual service and I'll run the same pass plus the repo's `detect_hazards.py` authz rules against it.