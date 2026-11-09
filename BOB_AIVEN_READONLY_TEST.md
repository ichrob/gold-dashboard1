# Bob: isolated Aiven PostgreSQL connectivity canary

This is not a database migration, backup, new simulation backend or live
service integration. The existing Render 5 GB production database stays
untouched. No scheduled or startup process imports this script. It does not
read or write simulation rows, move originals, change retention, or place orders.

The optional aiven_readonly_probe.py opens one short PostgreSQL session to an
*.aivencloud.com hostname, forces sslmode=verify-full with Aiven's project
CA, starts a READ ONLY transaction, checks SELECT 1, then disconnects.
It returns only a status code. Client errors, credentials, endpoints and
query results are never printed. There is no fallback to Bob's Render database.

## Operator prerequisites (not yet completed)

The Aiven free PostgreSQL service must exist. The Aiven service URI and
project CA certificate must be obtained from the Aiven service Overview.
An Aiven account session and its secrets are not exposed by the connected
GitHub/Render tools; do not paste passwords or complete connection URLs in
GitHub issues, PRs, chat, CI logs or public files.

For an isolated machine with psycopg[binary]>=3.2,<4 installed, securely set:

- BOB_AIVEN_TEST_DATABASE_URL: complete Aiven PostgreSQL URI, as a secret.
- BOB_AIVEN_TEST_CA_FILE: local path to Aiven's downloaded project CA certificate.

Then run: python aiven_readonly_probe.py

Expected: connected-read-only.
Other statuses mean no successful live connection has been demonstrated.
The included unit suite uses fake connections and does not access the network:
python -m unittest test_aiven_readonly_probe

This canary does not make the free service always-on. Aiven free is limited
to 1 GB storage and 20 connections with no pooler; Aiven may power off
inactive free instances. Do not migrate the production simulation families
or paper-trading evidence on the strength of this probe alone.

Next gates: secure provisioning of Aiven credentials + CA certificate,
verified live read-only connectivity, separately reviewed isolated test
schema, capacity/backups/recovery plan, and an explicit promotion decision.
No billing upgrade, secret upload, migration, or change to active service
environment variables is included in this PR.
