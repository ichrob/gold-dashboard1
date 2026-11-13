# Aiven Free host-RAM assessment without new services (13 November 2026)

Existing Bob already samples read-only PostgreSQL data every 30 minutes:
aiven_health.py, protected by the shared restore-target advisory lock.
Its latest verified samples had approximately 9.5 MB of database data,
1 current client, 20 max clients, 0 deadlocks and no long client queries.
**Those are SQL data, not Aiven host memory/OOM proof.**

Aiven's Free PostgreSQL service provides a one-node 1 GB RAM/1 GB storage
plan, a maximum of 20 connections, host metrics and logs in Aiven Console.
It has no support SLA and no separate integrations on the Free tier.
Operating-system and platform overhead mean the usable memory is lower
than the nominal 1 GB.

Aiven's Console Metrics tab (not PostgreSQL pg_stat_*) is the authoritative
source for RAM, CPU and disk. Its service Logs can verify OOM events. The
connected Bob/Render read-only tools do NOT expose that account's console
host metrics. Do not infer them from successful SELECT 1 or Render's own RAM.

New standalone aiven_host_capacity_review.py is an *offline, pure* evaluator
for a manually obtained, explicitly labeled Aiven Console sample. It only
reconciles one recent host sample with a time-aligned preexisting SQL health
sample; it does not fetch data, schedule jobs, run queries, resize services,
migrate data or authorize automatic restores/deletion. No credential, host
name, connection string or raw query is required. The output marks
memory-sample-unavailable and OOM cause unknown unless host evidence exists.

Expected private normalized dictionary from original Aiven Console:
source="aiven-console-host-metrics", observedAt=ISO-8601 timezone-aware,
memoryUsedBytes, memoryTotalBytes, optionally diskUsedBytes/diskTotalBytes
and only when separately confirmed in host logs: oomLogEvidence="confirmed".
Do NOT enter account tokens into the sample. This isn't an Aiven API schema,
nor evidence until genuine console measurements are supplied.

If a real, recent host sample reports >=80% memory or >=85% disk occupancy,
review memory/disk pressure. >=90% memory is a critical warning, not an
assertion of a real OOM. Never run parallel archives, enlarge work_mem,
issue VACUUM FULL, purge originals, upgrade to paid, or claim rescue from
SQL observations. Existing locks, small COPY segments, 2 MiB work_mem and
source/restoration independence remain unchanged.

Free plan official docs:
https://aiven.io/docs/products/postgresql/concepts/pg-free-tier
https://aiven.io/docs/platform/concepts/service-memory-limits

Offline test:
python -m unittest -v test_aiven_host_capacity_review.py

Release gate: full CI then genuine paired Aiven Console + Bob SQL measurement,
independent evidence review and no production data or schema changes.
