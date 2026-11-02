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
