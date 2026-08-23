File write wasn't approved, so here's the audit in-conversation.

**First, an important flag:** `benchmarks/fixtures/documents.ts` is an **eval fixture in this poka-yoke repo**, not a production service — its own header (lines 1–4) says hazards were planted deliberately. If you meant your real document service, point me at that path. The findings below are still worth having: they're exactly the shapes to grep for in the real code, but this file is not SOC 2 evidence.

**Verdict: your premise is true and it isn't protective.** `getDocument:14` and `Query.documents:25` are correctly scoped. **Six of the other seven paths are not.**

---

**1. `exportWorkspace:52` — no session at all + SQL injection.** Tenant comes from `req.body` (line 53). Any caller posts `{"tenantId":"<victim>"}` and exports their documents *and* comment bodies. No session is read anywhere in the function. And `$queryRawUnsafe` interpolates it (line 59), so `' OR '1'='1` returns every tenant in one request. **Today: None.** Device: tenant from session, drop `tenantId` from the input surface, `$queryRaw` tagged template — and scope the comments join too, not just `documents`. → **Control**. Then lint-ban `$queryRawUnsafe` repo-wide; that's the part that outlives the fix.

**2. `adminListDocuments:75` — an authn check wearing an authz costume.** `if (!session.userId) throw` proves someone is logged in. It never checks admin, never uses `session.tenantId`. Any user with an account gets 200 recent documents across all tenants. This is the one most likely to survive review, because the guard clause makes it *look* protected. Device: `requireRole` + `where: { tenantId: session.tenantId }` — admin means admin *of a tenant*. → **Warning**.

**3. `searchDocuments:65` — accepts `session`, never uses it.** No `tenant_id` predicate. Full-text search across every tenant, top 50 by relevance. Silent: it returns plausible, well-ranked results. (The `$queryRaw` here *is* parameterized — no injection, unlike #1.) Turn on `noUnusedParameters`; an unused `session` in a data-access function is a reliable tell.

**4. `updateDocument:41` — cross-tenant *write*.** `where: { id: documentId }` is the whole predicate. One tenant overwrites another's title/body. Integrity finding, not just confidentiality.

**5. `author:36` — `findUnique` with no tenant scope and no `select`.** Returns every column on the user row (email, password hash, anything added later). Doesn't open a door; turns each door above into a personal-data breach.

**6. `comments:30` / `attachments:33` — scoped by parent only.** Safe *today by accident*, because both current entry points happen to be scoped. Breaks the moment anyone adds a mutation payload or another field returning a `Document`.

---

★ Insight ─────────────────────────────────────
The tell that unites #3 and #4: both accept `session` and never read it. That's mechanically greppable and would have caught two of six for free.

Patching six sites fixes six sites. There are six because the unscoped query is the *short* form — one line vs two — so the incentive points at the leak. The durable fixes are **RLS** (`FORCE ROW LEVEL SECURITY` — your app user is usually the table owner, and set `app.tenant_id` per-transaction or a pooled connection leaks the previous request's tenant) and a **scoped repository** where tenant is a required constructor arg.

For the audit itself: two tenants, every operation from A against B's resources, assert **404 not 403** — a 403 confirms the resource exists, which leaks membership.
─────────────────────────────────────────────────

**One decision I need from you before I write any of it** — #4 has a genuine trade-off, because Prisma's `update` needs a *unique* `where`, so you can't just add `tenantId`:

- **A**: `updateMany({ where: { id, tenantId }})` + `if (count === 0) throw NotFound` — no migration, but silently no-ops if anyone drops the count check.
- **B**: `@@unique([id, tenantId])`, then `update` takes both — reaches **Control**, costs a migration.

I'd take B. Which do you want, and shall I retry writing the full report to `docs/poka-yoke/audit-2026-08-22-documents.md`?