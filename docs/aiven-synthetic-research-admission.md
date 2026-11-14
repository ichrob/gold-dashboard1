# Aiven research expansion: guarded synthetic readiness

Bob already reaches Aiven from Render. The live Aiven target is also used for
independent archive restore checks. It is **not** a spare gigabyte of RAM for
Render and not a safe destination for copying Bob's entire production database.

This change adds only a standalone, explicitly opt-in, one-session scratch
admission test. It does not run at service startup, change environment values,
create permanent tables, copy live rows, schedule checks, or use a paid plan.

## What a successful check proves

The target accepts one mutually excluded, TLS-verified write transaction,
two fixed **synthetic** values in a TEMP table, a readback, then an explicit
ROLLBACK. No transaction is committed; the connection closes afterwards.
The session advisory lock bob_restore_target_v1 protects ongoing restore
tests. Missing secrets, a Render-target URI, missing CA, a busy restore or
a failed query all stop without fallback.

The only documented success is synthetic-scratch-rolled-back. It does **not**
prove that a permanent research schema, dataset migration, retention policy
or source-RAM reduction would be safe. It cannot establish Aiven host RAM,
disk headroom, backup retention or future free-tier availability.

## Private operator prerequisites

Reuse the existing confidential BOB_AIVEN_TEST_DATABASE_URL,
BOB_AIVEN_TEST_CA_PEM (or BOB_AIVEN_TEST_CA_FILE) and DATABASE_URL
on a trusted isolated runner. Never place a URI or password in a chat,
issue, PR, CI log or committed file.

Only for a manually supervised single test, run:

    BOB_AIVEN_SYNTHETIC_CHECK=1 python aiven_synthetic_scratch_probe.py

The default is **disabled**; do not install it as a recurring job or service
startup hook. Fake-connector tests:

    python -m unittest -v test_aiven_synthetic_scratch_probe

## Promotion gates for any actual research offload

1. Check the independent restore use case and preserve its available disk/RAM,
   connection headroom and advisory-lock exclusivity; no new full-size restore
   attempt on the 1 GB free tier without independent capacity proof.
2. Confirm Aiven Console host RAM and disk readings, recent sample freshness,
   and free-tier conditions. PostgreSQL SQL counters alone are insufficient.
3. Use a separate low-privilege research role/schema with a strict size cap,
   bounded batches, encryption/sanitization policy and noncritical outputs.
4. Prove exact reconstruction and rollback from copies, then demonstrate
   measurable Render RAM/CPU/disk improvement with before/after evidence.
5. Keep live Gold signals, trades, push and every original record on Render;
   no source deletion, migration, paid upgrade or automatic activation.

A successful synthetic test is a preparation milestone only. Review separately
before merging any persistent data-writing workload.
