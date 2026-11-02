# PGDG client supply-chain validation (no production changes)

This workflow verifies `postgresql-18-repack` version
`1.5.3-1.pgdg12+2` for **Debian 12 / amd64** against PostgreSQL's
official **signed APT repository** in a throwaway Debian container.
The root signing-key fingerprint is checked against the official
PostgreSQL documented value before APT is allowed to trust the package.

The workflow verifies the exact package file size, extracts it, runs
`pg_repack --version` without any database connection, and prints
a public SHA-256 checksum for a later *strictly pinned* installer.

It does not install an extension on Bob, enable a maintenance job,
change the Render service build command, open DB networking or run a
table rewrite. The CI container and downloaded package are discarded.

Next: hard-pin the actual SHA-256 from this signed-index CI verification
and author a non-root extraction-only installer with strict version,
architecture, expected binary path and no database-touching functionality.
Only after full CI success should any deployment integration be considered.

## Existing Render service provisioning (opt-in, nonblocking)

The linked Render service's build command is currently `pip install -r
requirements-push.txt`; the connected Render app does NOT provide a
build-command edit action. To avoid modifying the service's build/start
commands or requiring repeated Shell steps, the existing Push startup has
an **optional** daemon bootstrap only when an operator sets
`BOB_REPACK_CLIENT_PREPARE=1` for the existing service. It runs after Bob
reports readiness and never blocks HTTP, scanner, push, trades or simulations.

The bootstrap fetches precisely one package from the official PostgreSQL
APT package host over TLS, requires the **exact SHA-256 validated by the
separate signed-index CI job**, file length and Debian package metadata
(`postgresql-18-repack`, PG18, amd64, 1.5.3-1.pgdg12+2), then extracts
**only** `/usr/lib/postgresql/18/bin/pg_repack` to a private user-owned
writable scratch directory. It verifies native ELF format and runs ONLY
`--version`. No `apt install`, system database extension, root privileges,
DDL, schema mutation or table-repack invocation is performed. A missing
libpq library, download failure, network redirect, wrong version or hash
simply records `BOB_REPACK_CLIENT status=client-unavailable` without changing
Bob operation. The scratch binary is ephemeral per Render instance and is
recreated on the next deploy if the operator flag remains set.

**This is toolchain provisioning only**, not permission to execute a table
repack. Separate work still needs verified table bloat, live WAL/scratch
headroom, traffic-window and lock plan, independent backup, matching enabled
server extension, and a new operator authorization. All reported actual
`diskBytesFreed` values remain null.
