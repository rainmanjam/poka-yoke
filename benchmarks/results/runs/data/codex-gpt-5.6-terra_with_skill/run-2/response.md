No. A non-empty-table test will pass while every joined value is `NULL` and then coerced to `0`—exactly the failure you saw.

For a revenue-critical model, gate publication on a small set of checks:

- **Required join-key / dimension null-rate:** assert the upstream join key and required joined revenue fields have ~0 unexpected nulls. This would have caught the rename before `COALESCE`.
- **Unmatched-join rate:** measure rows with no match; fail when it exceeds a tight, historically justified threshold.
- **Reconciliation:** compare dashboard/model revenue against the source-of-record total for the same period. This is the most important check because a wrong join can still produce plausible-looking, well-formed data.
- **Schema contract at ingest:** require the expected upstream column name, type, and nullability; a rename should fail/quarantine the load, not silently become nulls.
- **Volume and freshness bounds:** keep the non-empty test, but make it a floor/ceiling against comparable historical days and verify timely arrival.

Run these against staging and promote to the dashboard only if they pass. That is a **Warning** device: it stops publication at the moment the bad data is produced. The source-side schema contract is stronger still—closer to **Control**—because the renamed field cannot be accepted unnoticed.

Also treat `COALESCE(revenue, 0)` as suspect: only allow it when zero is a real business meaning, and separately assert that the pre-coalesce null rate is acceptable. Otherwise it converts an observable pipeline failure into a plausible lie.