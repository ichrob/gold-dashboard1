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


## Read-only capacity admission (new)

The separate pure evaluator aiven_research_admission.py does no SQL, makes no
provider calls, and never triggers the synthetic test. It returns a candidate
for **manual review only** when all these **real** source observations exist:

- Fresh Aiven Console host sample with project/service/node identity and
  measured RAM <=70% and disk <=55%. A missing Console metric blocks.
- Time-aligned recent Bob Aiven SQL sample: <=5 minutes old, validated
  20-connection ceiling with at most 3 current clients, no idle transaction
  and no long active clients. SQL database bytes do not replace host disk.
- Fresh (<=6 hours) original independent archive proof showing actual remote
  download, restore isolation, encryption and recovery-key verification.
- Requested nonproduction test budget strictly >0 and <=16 MiB.

Missing, stale, future, invalid, or contradictory evidence fails closed.
No percentages or server-memory bytes may be guessed from plan labels.
The success status candidate-for-manual-synthetic-test-only is **not** approval
for persistent research writes, a migration, or a new paid resource.
The evaluator accepts operator-supplied metadata; it does not authenticate the
provider source, so the owner must check original Console evidence independently.

Offline tests:

    python -m unittest -v test_aiven_research_admission

At the time of authorship, verified Aiven SQL and recovery checks are
available, but genuine Console host RAM/disk samples are **not** accessible via
the connected Bob/Render tools. Consequently the real Aiven pilot gate stays
blocked. Never synthesize these missing metrics just to pass the policy.


### Enforced capacity gate at the write boundary

The synthetic probe now also requires BOB_AIVEN_CAPACITY_EVIDENCE_JSON on the
trusted local runner. The value must be an object with named sub-objects
host, sql and archive, matching the input fields of
aiven_research_admission.assess. Operator supplies the **genuine** host fields
from Aiven Console and aligns them to Bob's recent SQL and restore receipt.
No passwords, URLs, tokens or personal information belong in this JSON.

A missing, stale, contradictory, high-memory, high-disk, high-connection or
incomplete evidence document returns capacity-evidence-unverified **before
the PostgreSQL connection is made**. The script remains disabled by default
even with valid evidence; its successful run can only test a temporary
synthetic table with explicit rollback.

The test suite uses invented local fixtures strictly to verify this
fail-closed rule. They are not host telemetry and can never be used to
authorize a real Aiven test. Real Console evidence has NOT been supplied
through the available integrations.


## Official Aiven REST service-metrics adapter (optional, no migration)

Aiven documents POST /v1/project/{project}/service/{service_name}/metrics as
a read-only host-telemetry operation requiring service:metrics:read. The CLI
documents mem_usage and disk_usage as percentages. The new
aiven_provider_host_metrics.py is NOT a server startup hook, and it does not
add paid resources, automatic polling, migrations or any PostgreSQL writes.

It is disabled unless BOB_AIVEN_METRICS_ONCE=1. The optional API connection
also requires privately supplied:

- BOB_AIVEN_METRICS_TOKEN: a short-lived Aiven API token limited to the service
  metrics read privilege, never the PostgreSQL password.
- BOB_AIVEN_METRICS_PROJECT: existing exact Aiven project identifier.
- BOB_AIVEN_METRICS_SERVICE: existing exact Free PostgreSQL service identifier.

The adapter pins the API address to https://api.aiven.io, uses TLS, makes
one bounded POST request only to fetch an hour of metrics, rejects redirects,
caps response size, and redacts credentials and account identifiers from CLI
output. Unknown chart shape, missing series, timestamps older than 20 minutes,
misaligned RAM/disk samples and units below 1% which could be ratios all fail
closed instead of being guessed. The normalized source is explicitly
aiven-service-metrics-api, never falsely identified as a Console screenshot.
The service-wide reading does NOT show individual process RSS/OOM evidence.

With BOB_AIVEN_METRICS_ONCE=1 in the manual synthetic probe, provider host
measurements replace the operator-entered host data. If that API check fails,
the probe blocks even when its manually entered values look safe. The SQL
health and independent recovery metadata still require fresh, authentic
evidence; an API token alone does not approve a test.

No Aiven API token, project identifier, or service identifier is available to
the linked ChatGPT tooling in this conversation. Thus **live provider-metrics
read is NOT yet confirmed** and the host-capacity gate is presently BLOCKED.
The credentials must be provided privately through an authenticated system,
not in a public commit, chat, issue, or CI log. Do not assume a normal
PostgreSQL user/password grants Aiven service-metrics API permissions.

Offline tests:

    python -m unittest -v test_aiven_provider_host_metrics test_aiven_research_admission test_aiven_synthetic_scratch_probe

This optional adapter is designed to be validated against the **actual**
service-metrics response schema after authorized credentials become available.
An unfamiliar provider JSON schema keeps the pilot blocked, and must not be
silently mapped to percentages.
