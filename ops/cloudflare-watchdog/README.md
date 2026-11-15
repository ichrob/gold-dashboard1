# External clock for Bob issue #940

Starts the existing `bob-self-healing.yml` on `main`; it does not implement
another repair worker, access market data, restart Render or create orders.
Initial configuration is **observation only** (`ENABLED=false`). No existing
GitHub trigger is removed by this change.

## Current staging status (2026-11-08)

The existing `bob-watchdog-clock` Worker is deployed in Cloudflare, the
`CLOCK` Durable Object is bound, and the Cron trigger
`4,14,24,34,44,54 * * * *` has been added and independently read back.
`ENABLED=false` and there is no `GITHUB_TOKEN` secret. In this unarmed state,
Cron invocations report `observation_only_no_token` to `last_check` instead of
failing merely because credentials have not yet been installed. This is a
**Cloudflare clock observation only**, not evidence that GitHub ran the watchdog.
The repository's native GitHub schedule remains unchanged.

The tested tokenless-observation fix was deployed to Cloudflare as Worker
version 2 on 2026-11-08. An authenticated re-read confirmed the new guard,
`ENABLED=false`, the unchanged `CLOCK` binding, and the existing Cron trigger.
No GitHub dispatch has occurred. A configured Cron is not itself proof of a
successful Cron invocation, and the recovery gate remains open.

## Deploy and acceptance

1. Use the owner's Cloudflare **Workers Free** account. SQLite-backed Durable
   Objects are available on Free. Do not enable a paid plan.
2. Create a fine-grained GitHub token limited to `ichrob/gold-dashboard1`,
   with `Actions: write` (and mandatory metadata read), a finite expiration,
   and no contents or issues write permission. Store only via Cloudflare's
   secret input as `GITHUB_TOKEN`; never put its value in git, chat or logs.
   GitHub executes the existing workflow with its existing GITHUB_TOKEN.
3. From this directory, use official Wrangler: `npx wrangler deploy`, then
   `npx wrangler secret put GITHUB_TOKEN`. The secret command prompts securely
   in the owner's terminal. Do not paste the value into a model-visible tool.
4. Observe at least one Cron event in Cloudflare logs. API errors and
   inconsistent listings fail closed. Check `last_check` in the DO storage.
5. Set `ENABLED` to `true` in configuration, deploy, and verify an actual
   `workflow_dispatch` run in GitHub, its exact revision, and completed monitor
   job. `dispatch_accepted` only means API acceptance, not job success.
6. After that proof, remove only `on.schedule` from the existing GitHub YAML
   through a tested PR. Retain workflow_run, push, workflow_dispatch and the
   existing concurrency group. Never disable the whole workflow.
7. Verify multiple real dispatches and successful jobs over at least two hours,
   with no duplicate monitor executions or unexplained gaps. A recent success
   from another trigger intentionally defers the clock until a later tick.
   Keep #940 open until this acceptance evidence is recorded.

Rollback: set `ENABLED=false` and restore the original GitHub schedule
`4,14,24,34,44,54 * * * *` if it was removed. No data deletion is needed.

## Guarantees and limits

- Singleton Durable Object serializes external checks. A persistent attempt
  marker is written before POST. Same-slot repeats, restarts and uncertain
  dispatch responses cannot immediately re-submit. A later tick rechecks GitHub.
- Waiting/running runs and successes less than ten minutes old suppress dispatch.
- API errors block dispatch rather than guessing. No secret/response-body logs.
- Public HTTP has no dispatch route; only the Cron binding calls the DO.
- During staged coexistence, a native schedule/push can race the external read.
  Existing GitHub concurrency prevents overlap, but not sequential duplicates.
  This is why the old schedule is removed after the external path is proven.
  GitHub API reads plus POST are not an exactly-once transaction.
- An uncertain accepted run hidden from GitHub's listings beyond the ten-minute
  cooldown can still cause a later duplicate; do not claim absolute exactly-once.
- No hard realtime or uptime guarantee; GitHub API/runner failures still apply.
- Token expiry/revocation requires secure renewal; errors appear in Cloudflare.

Validation: `node --test ops/cloudflare-watchdog/worker.test.mjs` from repo root.
Then run official Wrangler `deploy --dry-run` to validate bindings/bundle.

Sources: https://developers.cloudflare.com/workers/configuration/cron-triggers/
https://developers.cloudflare.com/durable-objects/platform/pricing/
https://developers.cloudflare.com/workers/configuration/secrets/
https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event

## Nachtrag 11.11.2026: Vorbereitung nach GitHub-Rebase

Die bestehende Cloudflare-Installation bleibt bis zur nutzerseitigen sicheren
Token-Eingabe strikt bei `ENABLED=false`. Der externe Auslöser benötigt ein
nur für `ichrob/gold-dashboard1` gültiges Fine-Grained-Token mit Actions:write,
keinen Tokenwert in Chat, GitHub oder API-Protokollen. Nach Secret-Readback
(nur Name), kontrollierter Aktivierung und echten `workflow_dispatch`-Läufen
werden mindestens zwei Stunden Laufkonsistenz geprüft. Vorher den nativen
GitHub-Cron nicht entfernen. Keine kostenpflichtige Cloudflare-Änderung.

## 11 November 2026 live activation observation

The owner securely installed a GitHub fine-grained Actions token directly as
Cloudflare `GITHUB_TOKEN` (only the secret name was read back). A controlled
`ENABLED=true` settings patch kept the Durable Object and secret bindings.
The first real scheduled Cloudflare tick on 11 Nov at 03:44 UTC returned the
sanitized `clock_check_failed`/`clock_tick_failed` outcome. No GitHub dispatch
success was observed. The clock was immediately reverted to `ENABLED=false`,
without removing the secret, Cron or existing GitHub native fallback.

Security fix: disabled workers now remain fully observation-only even when a
secret is present. An explicit non-dispatching `DRY_RUN=true` can diagnose
GitHub API connectivity while `ENABLED=false`; outbound network errors and
invalid JSON are classified using fixed redacted codes, never raw response
bodies or token values. Do not declare completion or remove GitHub's native
schedule until an actual external `workflow_dispatch` monitor run succeeds and
repeat observations span two hours. The earlier 03:44 failure remains an
unknown transport/runtime error until the next safe diagnostic observation.

## Bounded outbound diagnosis (11.11.2026)

After documented `github_network_unavailable` during read-only GitHub-API
access, diagnose egress without touching the existing owner secret. Only while
`ENABLED=false`, an operator may temporarily set `DIAG_UNAUTH=true`. The
existing Durable Object then runs **once** against GitHub's public fixed
`/zen` URL: one minimal `fetch`, and only after each HTTP response up to three further
GETs adding Accept/User-Agent, then redirect mode, then AbortSignal separately.
A durable pre-attempt marker makes the probe one-shot; the response body is
never read, retained or logged, and the token is never sent. Results are only
numeric HTTP statuses or fixed redacted failure categories. No workflow can
be dispatched in this mode. Restore `DIAG_UNAUTH=false` after observing the
single result. An error is evidence of the specific observed probe step, not
proof of invalid GitHub credentials or a general GitHub outage.

## Confirmed redirect-mode incompatibility (11.11.2026)

A real Cloudflare Cron at 04:34:10 UTC performed the once-only tokenless
GitHub outbound probe. The plain GitHub GET and the GET carrying ordinary
Accept/User-Agent headers returned valid HTTP responses. The next step,
adding `redirect: 'error'`, failed before an HTTP response and produced the
redacted code `github_network_unavailable` at step `redirect`. Therefore the
prior generic network warning did **not** prove blocked outbound networking or
an invalid fine-grained PAT. The exact underlying redirect target was not
captured and is not assumed.

The worker now uses `redirect: 'manual'` for every authorized GitHub GET
and the workflow-dispatch POST. In this mode Cloudflare must return a 3xx as
an HTTP response; existing strict success-status checks reject it without
following the Location target or forwarding credentials. No automatic redirect
and no new scope is allowed. The tokenless probe is already persistently
consumed; do not reset it. A separate disabled, read-only `DRY_RUN` and
actual `workflow_dispatch`/monitor receipts remain mandatory before declaring
end-to-end success. Preserve the native GitHub schedule until accepted.

## Run-list consistency follow-up (11.11.2026 04:44 UTC)

The first scheduled authenticated read-only probe after the safe redirect-mode
patch confirmed that Cloudflare reached the GitHub API using the owner token.
The request was rejected by Bob's own previous six-filter response invariant
with `inconsistent_run_list`; **no GitHub workflow dispatch occurred**.
A filtered GitHub response did not meet the strict count/page agreement; this
is a list-quality observation, not proof that GitHub CI or Bob itself failed.

The existing worker now requests **one** bounded, unfiltered-by-status latest
page for only workflow 382076329 on `main` (50 rows maximum) instead of six
separate status filters. Identity, final timestamps, active run status, recent
successes and recent nonsuccessful executions are checked independently.
Unknown/malformed data still fails closed; an active or recent run suppresses
new dispatch. An old active run outside the bounded page is not independently
excluded; the existing GitHub concurrency group continues to enforce safety.
The change never assumes total_count is a verified complete history and never
permits an unsafe redirect. Do not remove native GitHub Cron until live
workflow_dispatch and monitor evidence across the owner-approved window.
