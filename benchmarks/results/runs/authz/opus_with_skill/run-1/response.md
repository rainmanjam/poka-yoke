File write and the detector run both needed approval this session, so here it is in the conversation instead.

Used **`poka-yoke:authz`** (routed from the poka-yoke router: multi-tenant / cross-tenant leaks), reporting in `poka-yoke:audit`'s finding structure. I read all 78 lines by hand — `scripts/detect_hazards.py` needed shell approval, so nothing below came from tooling.

**First, two things about the artifact.** Line 1 declares it an *eval fixture for tenant isolation*, and lines 3–4 pre-announce the seeded hazards — this is benchmark input for this repo's A/B harness, not a running service. The findings are real as written, but "we fixed documents.ts" is not SOC 2 evidence. I've reviewed it fully anyway.

**Your premise is half right, and the half that's right is the trap.** The three obvious read paths *are* scoped from the session, correctly:

| Path | Line | Scope |
|---|---|---|
| `getDocument` | 15–17 | `session.tenantId` ✓ |
| `Query.document` | 22–23 | delegates ✓ |
| `Query.documents` | 25–26 | `ctx.session.tenantId` ✓ |

Four of the nine exported paths are not scoped at all.

---

### 1. `exportWorkspace` takes its tenant from the request body — Max/Trivial · `:52–63`
POST `{"tenantId": "<any other tenant>"}` and you get their whole corpus joined to every comment body. Three defects stack: **tenant scope is client-controlled** (`req.body`), **there is no authentication at all** (no session ever read), and **`$queryRawUnsafe` interpolates it** — so `' OR '1'='1` dumps every tenant even after you fix the first two. Silent; the response is shaped like a legitimate export. **Today: None.**

### 2. `adminListDocuments` authenticates but never authorizes — Max/Trivial · `:75–78`
`if (!session.userId)` proves someone is logged in and proves nothing about what they may see. No role check, no tenant predicate, no projection — any signed-in user of any tenant gets 200 full document rows system-wide. "Admin" almost always means admin *of a tenant*. **Today: None.**

### 3. `updateDocument` writes by ID with no tenant predicate — Max/Forgetting · `:41–50`
`session` is accepted on line 42 and never referenced. Cross-tenant **write** — original content gone, response indistinguishable from a legitimate edit. Prisma's `update` needs a unique `where`, so the fix is `updateMany({where:{id, tenantId}})` + assert `count === 1` → **404, not 403** (403 confirms the row exists). **Today: None.**

### 4. `searchDocuments` searches every tenant — High/Trivial · `:65–73`
`session` accepted, never used. Returns IDs and titles from all tenants, top 50. The SQL *is* a properly parameterized tagged template — not injectable; the defect is purely the missing `AND tenant_id = ...`. **Today: None.**

### 5. Nested resolvers inherit no tenant constraint — High/**Latent** · `:29–38`
Being precise rather than inflating: **not currently exploitable**, because both parent queries are scoped. The hazard is structural — `comments`/`attachments`/`author` trust `parent.id` and enforce nothing, so isolation rests on every present *and future* Document-producing path being scoped. `Document.author` also returns an unprojected user row.

**The chain worth showing your auditor:** #2 hands you other tenants' document IDs → #3 overwrites them. No ID guessing needed. And wiring #2 into the graph makes #5 live silently.

---

### The device, ranked by reach

Fixing all five locally leaves the unscoped query still the *shorter* thing to type.

1. **RLS** (Control, widest) — `ENABLE` **and** `FORCE ROW LEVEL SECURITY` (your app user is usually the table owner, and without `FORCE` the policy is decoration). Set `app.tenant_id` **per transaction** — a pooled connection carrying the previous request's value is a cross-tenant leak with extra steps.
2. **Scoped repository** (Control, type level) — tenant as a required constructor arg; raw `db` lint-banned from handlers.
3. **`noUnusedParameters: true`** (Warning, *one line*) — turns findings 3 and 4 into build failures today, for free. Cheapest device here by a wide margin.
4. **Two-tenant test** (Detection) — every operation from A against B's resources, assert 404. Write it *especially* if RLS lands, since RLS failures are silent and total.

`★ Insight ─────────────────────────────────────`
The tell in three of these five is a **parameter that is accepted and never used**. `session` appears in the signature of `updateDocument`, `searchDocuments`, and `adminListDocuments` — the author knew scoping belonged there and the body never followed through. That's why the compiler flag outperforms the code review: it detects intent-without-follow-through mechanically.
`─────────────────────────────────────────────────`

**One decision is yours, and it shapes the repository design:** does "admin" here mean *admin of a tenant* (scope it and add a role check — simple, closes #2 outright), or do you genuinely need cross-tenant support tooling? If the latter, the escape hatch needs its own audited, non-tenant-facing surface — and its shape determines whether the scoped repo can be Control or only Warning. Tell me which, and I'll write the repository plus the two-tenant test against it.

I've proposed rather than edited, per the skill. Want me to retry the report file and the detector with approval?