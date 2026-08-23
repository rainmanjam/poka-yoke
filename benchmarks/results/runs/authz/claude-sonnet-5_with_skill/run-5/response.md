Read both the router skill and the `authz` sub-skill (this maps directly — "Working on multi-tenant, permissions, or endpoints" / "can users see each other's data"). I audited `documents.ts` against its checklist. Your instinct on the main paths is right, but there are real gaps elsewhere — the file's own comment even hints at them.

## Findings (most severe first)

**1. `exportWorkspace` (line 52-63) — critical**
`tenantId` comes from `req.body`, not the session — client-controlled. There's no session/auth check at all in the function. And the SQL is built with raw string interpolation (`queryRawUnsafe` + `${tenantId}`) — that's SQL injection on top of the missing scoping. Anyone hitting this endpoint can request another tenant's `tenantId` and get their documents + comments back, or inject arbitrary SQL. This is the one an auditor would flag first.

**2. `adminListDocuments` (line 75-78) — critical**
Only checks `session.userId` is truthy — that's "is someone logged in," not "is this user an admin." No tenant filter at all: it returns the latest 200 documents across every tenant. Any authenticated user from any tenant can call this and see other tenants' documents.

**3. `updateDocument` (line 41-50) — high**
`where: { id: documentId }` — no `tenantId`. This is a write-path IDOR: any authenticated user who can obtain a `documentId` (including via findings #1/#2) can modify another tenant's document title/body. Writes are the classic blind spot the reads-get-reviewed-writes-don't pattern predicts.

**4. `searchDocuments` (line 65-73) — high**
No `tenantId` in the `WHERE` clause — matches across all tenants. Not SQL-injectable (Prisma's tagged-template `$queryRaw` parameterizes `${query}`), but `session` is accepted as a parameter and then never used for scoping — it's decorative.

**5. `Document.comments` / `Document.attachments` / `Document.author` nested resolvers (line 29-37) — lower confidence, worth a decision**
Each queries only by `parent.id`/`parent.authorId`, with no tenant check of its own. Today they're only reachable via an already-scoped parent document, so they're not independently exploitable — but nothing enforces that invariant. It's exactly the "child inherits nothing" shape the skill calls out: the moment any other path constructs a `Document`-shaped parent without tenant scoping (a batch job, a differently-scoped resolver, a future refactor), these become leaks with no additional check to catch them.

**Confirmed safe:** `getDocument`, `resolvers.Query.document`, `resolvers.Query.documents` — all correctly scoped by `session.tenantId`. So the "main query paths" read is accurate; the holes are in the export/admin/update/search/nested-resolver paths, which is exactly where this class of bug tends to hide.

## What I'd propose as the fix (not applying yet — this changes the shape of the module)

- A `DocumentRepo` that takes `tenantId` in its constructor (per `authz` skill, Control rung) so `documents`/`comments`/`attachments` reads go through something that cannot be constructed unscoped — kills #4 and #5 structurally.
- `updateDocument` gets `tenantId` added to the `where` (or switched to a scoped repo method) — kills #3.
- `exportWorkspace` and `adminListDocuments` get tenant/role pulled from `session`, not `req.body`, and `exportWorkspace`'s raw SQL becomes parameterized — kills #1 and #2.
- A two-tenant test (per the skill): create tenant A and B, run every exported function/resolver from A against B's document, assert 404 across the board. That's what proves this for the audit rather than asserting it.

Want me to implement these fixes, or do you want to route the `updateDocument`/search fix decisions to your team first (compound index vs. `updateMany`-style scoping, and whether the search SQL should move to a scoped view)?