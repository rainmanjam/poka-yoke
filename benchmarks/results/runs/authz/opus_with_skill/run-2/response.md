File write needs approval too, so here it is inline.

**Your assumption holds for the paths you were thinking of** — `getDocument`, the `document`/`documents` resolvers are scoped correctly (`:14`, `:22`, `:25`). That's exactly why the rest reads as safe. Six findings, ranked:

**1. `exportWorkspace:52` — tenant ID comes from `req.body`.** No session is read anywhere in the function. Send `{"tenantId": "<any other tenant>"}` and get that tenant's whole corpus joined to every comment body, HTTP 200. Worse, it's built with `$queryRawUnsafe` string interpolation — `' OR '1'='1` returns everything regardless of the tenant value, so deriving `tenantId` from the session alone wouldn't close it. Fix: session-derived tenant **and** `$queryRaw` tagged template. Control = `no-restricted-syntax` banning `$queryRawUnsafe`, plus banning `tenantId`/`orgId` as readable keys off `req.body` — a client-supplied tenant ID is never correct, so ban it categorically.

**2. `adminListDocuments:75` — authentication mistaken for authorization.** `if (!session.userId)` proves someone is logged in, nothing more. Returns the 200 newest documents *across all tenants*, so it leaks the freshest data preferentially. Needs both a role check and `where: { tenantId: session.tenantId }` — admin means admin *of a tenant*.

**3. `updateDocument:41` — cross-tenant write.** `where: { id: documentId }`, no tenant predicate. Any document ID overwrites that document. Silent, destructive, and the audit trail attributes the change to a user outside that tenant. Prisma needs `@@unique([id, tenantId])` (then the scoped form is the only compilable form — that one reaches Control) or `updateMany` + assert `count === 1`, throwing 404 not 403.

**4. `searchDocuments:65` — unscoped full-text search.** Tagged template, so not injectable, but no `tenant_id` predicate: an attacker-chosen term queries every tenant's corpus and ranking floats other tenants' best matches above the caller's own. Same tell as #2 — `session` is a parameter that's never referenced.

**5. `comments`/`attachments:30,33` — safe by accident.** Scoped on `parent.id` only; neither receives `ctx`, so neither *can* check the tenant. Safe only while every parent above them is scoped. The leak arrives with the first unscoped parent field and won't look like a change to these lines.

**6. `author:36` — full user row, unscoped, no `select`.** Whatever `User` holds is reachable through the graph, and clients pick fields.

**The structural point:** those six are one cause. `db.documents.findMany({})` is shorter than the correct version and passes every single-tenant test. Six `where` clauses fix six sites and leave the seventh available. Reaching Control means RLS (`FORCE ROW LEVEL SECURITY`, `app.tenant_id` set **per transaction** — a pooled connection carrying the last request's setting is the usual way RLS rollouts fail), or a repo whose constructor requires a `TenantId` with the raw `db` lint-banned from handlers.

**For the audit itself:** write the two-tenant test — every operation from A against B's resources, assert 404 for all, enumerate the route list programmatically. A dated, repeatable test is stronger CC6.1 evidence than any of these diffs, and it's what tells you the RLS actually works.

`★ Insight ─────────────────────────────────────`
The tell that recurs in #2 and #4 is a `session` parameter that's accepted and never dereferenced. That's mechanically detectable — an ESLint `no-unused-vars`-style rule scoped to parameters named `session`/`ctx` would have caught both at authoring time, which is a cheaper device than any review.
`─────────────────────────────────────────────────`

Two things I couldn't do: the detector script (`detect_hazards.py`) and the report file both needed approval this session — approve them and I'll re-run properly. And if you want the RLS-vs-scoped-repository call made concretely, tell me whether search must stay in raw SQL; that's the fact that decides it.