# Aiven restore diagnostics and test boundaries

The existing Aiven restore target remains separate from production. When its
configured URI passes the Aiven host/production inequality guard, the push service
samples fixed read-only PostgreSQL aggregates 90 seconds after startup, then every
30 minutes. `BOB_AIVEN_HEALTH_DISABLED=1` is an explicit off switch. No new account,
service, credentials, provider API or paid integration is required.

`BOB_AIVEN_HEALTH` log records include the UTC observation time, PostgreSQL start,
database bytes, aggregate connection counts, temporary disk counters and deadlocks.
No query text, rows, usernames, hostnames or exception messages are recorded.
The private storage view exposes the latest sample and findings. The process keeps
at most 48 samples (about 24 hours); this buffer resets on deploy. Render log
retention applies to log records. This is not a permanent telemetry database.

Host RAM, per-process RSS and kernel OOM records are unavailable through this SQL
path and always remain unknown. A successful SQL sample does not authorize an
automatic restore or prove that an OOM was fixed. Use the existing Aiven console
metrics/logs for host-level evidence; do not open firewall rules for SQL editor.

## Serialized, bounded restores

The existing source-side `bob_storage_maintenance_v1` session lock and durable
daily attempt ledger stay unchanged. Every `evidence_archive.restore_check` now
also takes `bob_restore_target_v1` on the target. This covers direct/manual calls
and multiple sources. A busy target fails before temporary tables are created;
the lock survives per-segment rollback and is released when the connection closes.
Health samples use the same lock and skip a busy restore, without retries.

Restore connections have a 5-second connection timeout, 120-second SQL timeout,
3-second lock timeout, 2 MiB work_mem, 16 MiB maintenance_work_mem and no parallel
query workers. Existing 32 MiB COPY segments, temporary-only tables, checksums,
exact reader comparisons and rollback between segments remain intact. These are
per-operation limits, not a promise to cap total server RSS or total restore time.

## Archive and storage experiments

Do not repeat successful archived restore receipts to demonstrate this change.
CI exercises exact PostgreSQL roundtrips, segmented cleanup and target locking
against its ephemeral PostgreSQL service. No original data or Aiven credentials
are supplied to CI. Existing source isolation, encryption, remote download,
independent restore and recovery-key gates remain mandatory before archival use.

PRs #1616 and #1618 already measured synthetic compression/reference cases; do not
merge or rerun them as a claimed production optimization. The next original-sample
comparison must use representative repeated subfields, retain every original
event/time, count all indexes and prove exact reconstruction. It additionally
requires fresh Aiven RAM/disk headroom and the existing shared maintenance lock.
Unknown host RAM cannot grant that approval. No physical Render savings have been
demonstrated by this diagnostic change; no production row cleanup is authorized by
its output. Large original-data experiments remain a separate acceptance step.
