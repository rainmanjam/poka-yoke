Couldn't write the report to `docs/poka-yoke/` (write permission not granted this session), so it's here instead.

---

**First, the thing that changes what this answer is worth:** `benchmarks/fixtures/documents.ts` is a benchmark fixture — its own header says the hazards are seeded deliberately. If your SOC2 scope is the real document service, this audit doesn't cover it. The findings transfer; the evidence doesn't.

**On your premise:** you're right that the main paths are scoped. `getDocument:14` and `Query.documents:25` are textbook-correct. That's exactly what makes the file dangerous — they set the reader's expectation for six other paths, four of which query across every tenant.

I couldn't run `detect_hazards.py` (needs approval), so this is the three lenses read by hand.

## Live cross-tenant paths

**1. `adminListDocuments:75` — no tenant filter at all.** Returns 200 most recent documents across the whole database, to any signed-in user of any tenant. `if (!session.userId)` is an *authentication* test in an authorization costume — and since `Session.userId` is non-optional `string`, it only ever rejects `""`. Fix: `requireRole` + `where: { tenantId: session.tenantId }`. → Warning alone.

**2. `exportWorkspace:52` — two independent defects.** `tenantId` comes from `req.body` (client-controlled — a tenant ID from the request is an attacker input, not an authz input), *and* it's interpolated into `$queryRawUnsafe`, so `' OR '1'='1` dumps every document plus comment bodies regardless. Fixing the first does not fix the second. Drop `tenantId` from the body schema, switch to the `$queryRaw` tagged template (binds), lint-ban `$queryRawUnsafe`.

**3. `updateDocument:41` — cross-tenant write.** `where: { id: documentId }`, no tenant; `session` accepted and never read. Disclosure *plus* silent corruption of another tenant's records, returning the modified row as if fine.

**4. `searchDocuments:65` — no tenant predicate at all.** Full-text search over every customer's documents, top 50, id + title. Not injectable (the tagged template binds `${query}` correctly) — purely the missing `WHERE tenant_id`. Titles are usually the most sensitive field in the row.

Findings 1 and 4 both take `session` and never use it. That's what makes them read as scoped.

## Lower

**5. `Document.author:36`** — unscoped `findUnique` with no `select`, so the whole user row (hash, MFA secret) loads into memory and logs regardless of what the SDL exposes.

**6. `Document.comments`/`attachments:29-34`** — latent, not live. Both parent paths are scoped today, so `parent.id` is already tenant-owned. That safety rests on an invariant nothing enforces: that every *future* path to a `Document` is scoped. Flagging it as latent deliberately — overstating it would cost you credibility on the four that are live.

## The actual fix

These are six instances of one condition. Patching six `where` clauses leaves the seventh available to whoever writes it next month. The question isn't "is this query scoped" but **"could an unscoped query even be written here"** — today it can, in one short line, and it passes every single-tenant test.

- **RLS** (`ENABLE` + `FORCE ROW LEVEL SECURITY`, policy on `current_setting('app.tenant_id')`) closes 1, 2, 4 and 6 at once and covers raw SQL. Catch that decides whether it works: set it **per transaction**, and make the middleware that sets it the only path to a connection — a pooled connection carrying the previous request's value is a leak with extra steps.
- **Scoped repo** — tenant as a required constructor arg, raw `db` lint-banned from resolvers. The device isn't the `where`; it's that the handler can't reach a client lacking one.
- **Branded `TenantId`** — makes finding 2a a compile error. Needs `strict: true` + `tsc --noEmit` required in CI, or it's just a comment.
- **Two-tenant test**, table-driven over the exports, asserting **404 not 403** (403 confirms existence, leaking membership). For SOC2 this *is* your CC6.1 evidence artifact — better than describing your query conventions.

I haven't changed any files.

★ Insight ─────────────────────────────────────
The tell in this file is the **unused `session` parameter**. `searchDocuments(session, query)` and `adminListDocuments(session)` both accept it and never read it — the signature advertises scoping the body doesn't do, so the call site looks correct and review slides past. `@typescript-eslint/no-unused-vars` with `args: "all"` would have flagged both at zero cost.
─────────────────────────────────────────────────

**One decision I need from you before touching finding 3.** Prisma's `update` requires a unique `where`, so adding `tenantId` forces a schema choice:

- **(a)** compound `@@unique([id, tenantId])` → `where: { id_tenantId: {...} }`, throws `P2025` → map to 404. Control, invariant lives in the schema where every service shares it. Costs a migration + a permanent index.
- **(b)** `updateMany({ where: { id, tenantId } })` then `if (count !== 1) throw new NotFoundError()`. Ships today, no migration — but the guarantee sits in application code, which is the F6 shape this method argues against.

I'd take (a). What I can't see from the file: whether `documents` is large enough that the migration needs a window, and whether anything besides this service writes to that table. If a script or second service does, (a) is the only option that protects it.