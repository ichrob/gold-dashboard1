# Disposable PostgreSQL 18 pg_repack rehearsal

This is a **strictly isolated** integration test running entirely in a
GitHub Actions Docker container, with fake connection credentials and
**synthetic text data** generated for testing. There is no access to
Bob's Render environment, source DB credentials, private Google Drive
archive or production images.

The workflow verifies an official signed PGDG Debian 12 APT index and installs
`postgresql-18-repack=1.5.3-1.pgdg12+2` only **inside** a throwaway container.
It temporarily creates the `pg_repack` extension there, creates synthetic
rows with deliberately bloated TOAST, and measures
`pg_total_relation_size` before and after a dry-run and a bounded
full-table repack. An aggregate row-content digest and row count must match
exactly before and after. If the relation does not actually shrink, the
test fails rather than claiming success.

For safety the invocation targets only
`--table=public.synthetic_repack_target` and database `ci_repack`;
`-D` means **do not kill conflicting backends**, `-T 2` shortens lock
acquisition, and `-j 1` avoids parallel index rebuilding. A 120-second
host timeout covers the disposable container command and the entire
container is removed in an unconditional cleanup step.

This rehearsal will **not** verify Bob's real storage reserve, free WAL,
live OCR/market/Push concurrency, current independent backups or Restore
integrity. No production DDL, pg_repack command, table copy, source
deletion or extra Render plan is authorized by its success.

Real physical volume reclamation remains explicitly blocked until separate
measured and reviewed authorization, with a durable original backup and
unambiguous table-specific before/after physical Render metrics.
Related: #1231, #1241 and #1246.
