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

## Browser-only handoff (Android Chrome; no new ChatGPT plugin)

1. In https://console.aiven.io/ open the existing PostgreSQL Free service,
   Overview -> Quick connect / Connection information. Copy the complete
   PostgreSQL URI locally (do not send it to chat, a GitHub issue or a PR).
   Also copy the project's CA certificate from Overview (the PEM is public
   certificate material, but keep the database URL and password private).
2. In https://dashboard.render.com/web/srv-daskbao473hc738n0k4g open
   **Environment** for **bob-private-scanner** (NOT bob-push-service).
   Add just these two service-specific environment variables:
   - BOB_AIVEN_TEST_DATABASE_URL = complete URI copied from Aiven.
   - BOB_AIVEN_TEST_CA_PEM = full PEM certificate including BEGIN/END lines.
   Render's environment editor accepts multiline values.
   If Android Chrome cannot paste PEM, as an alternative create a Render
   **Secret File** named `bob_aiven_ca.pem` under **Secret Files** and paste
   the PEM content there; the scanner reads `/etc/secrets/bob_aiven_ca.pem`
   automatically. In that case add only the URI variable.
3. Choose **Save only** to avoid an immediate restart before code review.
   Save only does NOT make secrets available to a running Render process.
4. When the new branch's changes are reviewed and merged, the scanner's next
   normal Render deployment executes ONE independent read-only probe (max.
   5 seconds for initial connection and a short SQL timeout). Render log:
   `BOB_AIVEN_CANARY status=connected-read-only` means a real successful
   probe. Any other result means connection is not yet proven.

Never replace `DATABASE_URL`, `PUSH_SERVICE_TOKEN`, archive credentials,
or existing service variables; never put Aiven credentials in GitHub files.
No paid plans. The probe does NOT move simulation data or create tables.

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
No billing upgrade, migration, or change to active service environment\nvariables is automatically applied by this PR. Aiven credentials are configured\nseparately by the owner through Render's private browser dashboard.
