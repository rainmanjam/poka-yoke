No. A non-empty revenue table only catches total pipeline failure; it will pass when every join misses and revenue is silently converted to zero.

Add controls that fail closed before `COALESCE` masks the problem:

- **Schema contract:** assert the upstream column exists, has the expected type, and alert on added/removed/renamed fields.
- **Join quality assertion:** require a minimum match rate and fail if the join key or revenue field becomes unexpectedly null. Track unmatched rows separately.
- **No blanket zeroing:** preserve `NULL` as “unknown/broken” through transformation; only coalesce to `0` where zero is a documented business meaning.
- **Reconciliation:** compare dashboard revenue with an independent source of truth (billing/ledger), with an agreed tolerance. Alert on material variance.
- **Freshness and volume checks:** ensure inputs arrived, row counts are within historical bounds, and revenue is not anomalously low relative to normal patterns.
- **Alert routing and ownership:** page or notify the data owner when these checks fail—don’t rely on someone noticing a chart.

For this incident, the highest-value test looks like:

```sql
assert joined_rows > 0;
assert source_rows > 0;
assert joined_rows / source_rows >= 0.99;
assert count_if(source_revenue is not null and joined_revenue is null) = 0;
```

Pick thresholds that fit your data, but make the failure explicit. Then prove the device: temporarily rename or remove the join column in a test fixture and confirm the pipeline/check goes red.