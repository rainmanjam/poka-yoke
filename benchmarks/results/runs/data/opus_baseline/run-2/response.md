No. Your test would have passed on all 21 days of the incident.

The table wasn't empty. It was full of rows whose value was `0`. That's the failure mode this repo's CLAUDE.md calls a check that cannot fail — it went green during the outage, so it's a rumour, not a device. Before you keep it: reproduce the incident (rename the column in a fixture, re-run), watch the test stay green, and let that be the evidence for what follows.

**Run the four questions against your incident:**

| Question | Would it have caught this? |
|---|---|
| Is it there? (freshness) | No — the table was fresh. It was being written on time, with wrong values. |
| Is there the right amount? (volume) | No — row counts were normal. The join returned rows, just null ones. |
| Is it shaped right? (validity) | **Only if you check before the COALESCE.** Afterwards `0` is a legal revenue value. |
| Does it agree? (reconciliation) | **Yes.** Warehouse total vs. the source billing system diverges on day one. |

The `COALESCE(x, 0)` is the actual hazard. It converts *unknown* into a legal, plausible, silently-wrong value — the data equivalent of `except: pass`. Nulls were your signal and you erased them before anything could look.

**In priority order:**

1. **Reconciliation on revenue** — sum the warehouse against the source of truth, daily. This is the only one of the four that catches logic errors; a wrong join produces perfectly well-shaped wrong data.
2. **Assert the null rate *before* coalescing.** Either drop the COALESCE entirely and let `NULL` propagate loudly, or gate it: `null_rate(amount) < threshold` fails the build, and only then do you default.
3. **Reorder so the check can stop the pipeline.** Build to staging → assert → promote on pass. If tests run after publish, bad numbers reach finance regardless of how good the tests are. This is usually free — no new tooling, just DAG ordering.
4. **Contract at the boundary.** Select columns explicitly so an upstream rename errors instead of yielding nulls, and treat rename as drop-plus-add, because that's what you experienced.
5. **Surface last-updated and last-reconciled on the dashboard itself.** Three weeks of silence is a UI failure too.

★ Insight ─────────────────────────────────────
Freshness, volume, and validity all validate *shape*. Your incident was shaped perfectly — that's why it survived three weeks. Reconciliation is the only lens that compares against an independent source, which is why it's the one to install first on money tables.
Note that in most columnar warehouses these land on the Detection rung, not Control — the bad row is already written. Only a real `NOT NULL` constraint prevents it.
─────────────────────────────────────────────────

**One decision is yours, and it shapes the device:** what should reconciliation do on a breach? Exact match blocks on legitimate timing skew (payments settling across a day boundary); a tolerance band risks a slow drift hiding under it. And on breach — block publication, or publish with a banner? Blocking means finance sees no dashboard rather than a wrong one.

Tell me your warehouse and orchestrator (dbt? Airflow?) and your answer to the tolerance question, and I'll write the assertions plus the failing-first test that proves each one catches the rename.