# Physical PostgreSQL storage reclamation: guarded preflight only

## Why this path
Private Bob storage metrics on 2 Nov 2026 show a **686,571,500 B** physical
Render volume and a **576,624,319 B** logical PostgreSQL database.
`bob_improvement_observations` occupies about **66.8 MB**, including
approximately **52.9 MB of TOAST allocation**. This is allocation, not
verified bloat or guaranteed savings.

The Android image table is only about 16.3 MB and therefore cannot provide
a lasting large-capacity fix on its own. Old analysis and metric payloads
are already being independently archived, yet PostgreSQL may retain reusable
internal pages rather than returning bytes to Render.

Render documents `pg_repack` for PostgreSQL 16+ as an online physical
compaction method. Bob uses PostgreSQL 18. It is NOT equivalent to normal
`VACUUM`. Online reorganization still creates a copy, writes WAL and can
briefly lock the target. Render requires **free disk greater than twice**
the target table+index bytes, and a client with a matching extension version.
Reference: https://render.com/docs/postgresql-pg-repack

## What is installed by this change

`python -m storage_repack_preflight preflight`

This is **read-only** and is the ONLY recognized CLI command. It checks one
fixed allowlisted historical table, PostgreSQL major version, total relation
size, primary-key availability, `pg_repack` extension installation and
presence of a matching client executable. It reuses the existing private
24h verified archive receipt and bounded Render provider disk metric.

A strict preliminary capacity heuristic subtracts twice the full relation
size from measured free capacity, then requires over **120 MB additional
reserve**, with the database volume under **750 MB** and target relation
under **100 MB**. That check does not measure current WAL file peaks,
long-running transactions, indexes under concurrent workloads, the size of
a temporary repack transaction or actual recoverable table bloat. For this
reason, the result ALWAYS returns `readyToExecute=false`.

The output only contains booleans, size counters, a fixed public table
name and generic states. No DB URLs, secrets, original user/evidence rows
or private Drive file identifiers are printed or logged.

## What is NOT authorized

There is **no** `execute` verb, no extension installation, no pg_repack
command, no physical rewrite or destructive SQL, no environment switch,
startup trigger, scheduler or Render deploy action. No table rows,
simulations, archived evidence or 24h image retention are changed.

Before any real repack, separately establish table bloat with a safe
read-only measurement, independently confirm sufficient actual WAL/scratch
headroom and restore proof, test full reader availability while repacking,
choose a quiet maintenance window and obtain explicit one-table authorization.
A temporary table copy can fill a 1 GB database disk if WAL or connection
activity exceeds reserves. A normal `VACUUM` often makes space reusable
inside PostgreSQL without reducing provider-reported disk usage.
All `diskBytesFreed` values stay `null` until a provider-level physical
before/after metric actually proves a change.

Refs #1231, #1222 and the current database-forensics documentation.
