Short answer: merge and deploy the **code** this afternoon if you want; don't run the **column drop** on a Friday. Split them.

The "it's small" framing is about the diff size. The thing that matters for a Friday deploy is the rollback story, and this PR has two very different ones bundled together:

| Part | If it's wrong | Rollback |
|---|---|---|
| Update the three readers | Something 500s | Revert the deploy, minutes |
| `DROP COLUMN legacy_email` | Something you didn't know about reads it, or you need the data | Restore from backup, hours, and you lose writes since the snapshot |

Things CI green does **not** tell you, because tests only exercise the readers you already found:

- **Readers outside the codebase.** Reports, BI/ETL jobs, ad-hoc SQL someone saved, a cron script, another service sharing the DB, a DB view or trigger or index that references the column. `grep` found three in *this* repo; it can't see the others.
- **`SELECT *` / ORM column lists.** Some ORMs cache the schema or explicitly enumerate columns; a stale process that started before the drop can fail on the next query.
- **Deploy ordering.** If the migration runs before the new code is live (or on one instance before another in a rolling deploy), old code is still reading a column that's gone. And if you roll the code back after the drop, you've reintroduced readers of a dead column — the code rollback itself breaks.
- **DB engine behaviour.** Postgres `DROP COLUMN` is a quick metadata change; older MySQL can rewrite the whole table under a lock. Worth knowing which you're on before doing it on a table of any size.

What I'd actually do:

1. **Today:** merge and deploy the three code changes only. Fully reversible, and it proves in production that nothing *you* own still reads the column.
2. **Monday/Tuesday morning**, with people around: run the drop. If you want a cheap safety net, rename it to `legacy_email_deprecated` first and leave it a week — anything still reading it fails loudly, and un-renaming is instant. Drop after that.
3. Before the drop, check `pg_stat_user_tables`/query logs or whatever your DB offers for recent reads of that column, and grep any repos that share the database.

`★ Insight ─────────────────────────────────────`
This is the expand/contract pattern: schema removals lag code changes by at least one deploy so every step stays individually reversible. The reason "small change, Friday" is a trap here isn't superstition — it's that a column drop converts a code-rollback problem into a data-restore problem, and those have very different recovery times.
`─────────────────────────────────────────────────`

If you tell me which database and whether anything else shares it, I can be more specific about the locking and the rename-first step.