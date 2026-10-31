# Decision-audit storage: read-only field footprint and archive gates

## Confirmed production state (31 Oct 2026, 14:48 UTC)

The private storage catalog measured `bob_decision_audit` at **139,796,480 allocated bytes**:
9,371,648 heap, 7,577,600 indexes, 122,814,464 TOAST and 32,768 other.
The catalog's estimated row count was 276; estimates are not exact counts and
relation allocation is not a measurement of reclaimable space. The independent
Render-volume meter was at 689,557,500 bytes. No data was removed here.

## Why direct JSON-pointer replacement is unsafe

The original `bob_decision_audit.payload` is used by *SQL*, not only Python.
Any generic replacement with a Drive reference would silently change:

- The `bob_audit_evaluable_cursor` and prospective indexes whose predicates
  inspect `marketEvaluable`, `recordedAt`, `reviewVariants`, `origin`,
  `direction` and `ruleVersion`.
- The recent and seven-day outcome harvest, which tests `marketOptimization`
  and `entryQuality` and derives original recorded time from JSON.
- The 30-day prospective query and its bounded 24-hour fallback.
- Day-history summaries, first qualifying signals, full page reads and
  comparative reviews in `audit_history` and `decision_audit`.
- Exact record and evidence consumers in other subsystems that must be
  enumerated before a write-side change.

Historical decisions may be used to compare simulation and product selection.
Do not modify original timings, numeric values, eligibility, directions, or
gates as part of storage optimization.

## New diagnostic

`storage.layout.decisionPayloadSample` is read-only and explores at most
four oldest and four newest immutable audit rows, deduplicating their IDs.
It aggregates nested JSONB sizes into a fixed list of field groups and
`other-fields`. It returns *no* raw evidence, source URL, original JSON key
outside the fixed allowlist, ISIN, price, credential or payload. It returns
`not-observed` if the table is absent or the query fails. This is not an
exact survey or direct physical TOAST storage measurement.

PostgreSQL integration regressions assert an eight-record bound, the absence
of original values in the result, read-only behavior, missing-table isolation,
and empty-table handling.

## Preconditions for a future lossless offload

1. Map every SQL predicate and reader of the original payload across the entire
   repo, including adjacent tests and background workers. Do not assume the
   audit history reader is the only consumer.
2. Choose a field-level split only after sample sizes identify the large
   children; retain SQL-dependent fields *inline* unchanged.
3. Keep original row identity, clocks, outcomes, and numeric JSON serialization.
   Upload encrypted/private immutable Drive chunks, verify SHA-256 by remote
   download, compare original reads, and commit atomic compare-and-swap pointers.
4. Maintain exact read-through for each report, replay and historical lookup;
   raise an explicit incomplete result on missing/corrupt remote chunks.
   Roll out compatible readers on **both** services before enabling any writer.
5. Compare PostgreSQL TOAST, heap, indexes, full logical DB and independent
   Render volume after a documented safe maintenance window. Offload and
   deleted TOAST chains do not automatically produce volume free space.
6. Require PostgreSQL integration, original-row equality, numeric precision,
   indexed predicate consistency, concurrent replay and rollback tests,
   restored-backup proof and error-path tests. Preserve app availability:
   earlier index maintenance caused transient database lock and timeout errors.

There is **no audit archive writer or automatic compaction enabled** by this
measurement-only change. It performs no orders, data deletion, paid scaling or
retention shortening.
