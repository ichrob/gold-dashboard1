# Personal DEGIRO holdings connection

Prepared under Mehr → DEGIRO → DEGIRO über SnapTrade Personal. The first real
account connection still requires the account owner to create/verify a free
SnapTrade Personal account, link DEGIRO for reading, enable SnapTrade 2FA and
create the Personal client ID and consumer key. No commercial user registration,
paid plan, card, broker password, or TOTP master key is collected by Bob.

The authenticated, same-origin configuration form encrypts the Personal key with
Fernet, domain-separated from the existing PUSH_SERVICE_TOKEN. Only ciphertext
is stored in the existing private bob_settings table via fixed, service-token
authenticated settings endpoints. Keys are never returned or logged. Changing
the service token requires re-entering the Personal key. Deletion clears the
saved key and local snapshot and invalidates in-flight responses. This does not
revoke a provider connection; the user manages that in the SnapTrade dashboard.

The web process starts one independent, idempotent background reader using the
existing worker maintenance loop. Without a saved key it makes no SnapTrade
requests. After configuration, authenticated use of the DEGIRO panel permits a read at most
every 600 seconds. Without active panel use, the worker uses a six-hour cadence
(maximum four background snapshots per 24 hours); the existing independent
30-second issuer quote process remains separate. Errors retain the previous snapshot as unconfirmed;
there are no immediate login retries. SnapTrade 429/402/401/403 errors are fixed
labels without remote messages. A failed settings-store load is retried at most
once per minute. Stored setup survives web restarts; financial snapshots are
process-local and are fetched anew after restart.

Only GET to api.snaptrade.com is supported, with redirects disabled and a fixed
path allowlist: /authorizations, /connections/{uuid}/accounts,
/accounts/{uuid}/positions/all, /accounts/{uuid}/balances/v2. API-key requests use
the exact-path canonical HMAC signature used by the current official SDK, with
clientId and timestamp; no userId/userSecret. Only DEGIRO connections of type
read are accepted, bounded to three accounts. There are no order, quote,
connection-refresh, transaction-sync or billing calls. Personal/free status is
explicitly affirmed by the owner; Bob does not assert that its read-only API
can independently guarantee future vendor pricing. No plan is purchased.

Original data_freshness.as_of is retained independently for cash and positions.
Both institution and SnapTrade freshness modes must be realtime and original
timestamps within the documented 10-minute holdings interval for the holdings
fresh flag. HTTP success, request time and cached snapshots never become quote
timestamps. Disabled connections are never queried for supposedly fresh data.
Only normalized fields enter Bob's authenticated view; account numbers, raw
responses, provider keys and connections are not exposed in diagnostics.

Gold knock-out coverage, ISINs, bid/ask source times, leverage, KO validity,
Swiss account eligibility and full holdings completeness remain unverified.
The documented current instrument schema has symbols/FIGIs rather than an
ISIN field; Bob leaves identity unverified instead of guessing a mapping.
Positions (including factors if held) are informational only. They never enter
the gold candidate ranking, execution approvals, MyTrade or paper ledger.

## Sources checked 2026-10-21

- https://snaptrade.com/personal — free Personal API for one's own accounts
- https://snaptrade.com/brokerage-integrations/degiro-api — read-only DEGIRO
- https://docs.snaptrade.com/docs/personal-vs-commercial — no Personal user registration
- https://docs.snaptrade.com/docs/realtime-data — recommended polling >=10 minutes
- https://docs.snaptrade.com/docs/syncing — transactions daily/delayed
- https://support.snaptrade.com/brokerages — account/asset coverage caveats
- https://github.com/passiv/snaptrade-sdks — current default API host, exact-path
  request_after_hook signature and positions/balances schema

## Validation

Unit/HTTP tests check encryption/reload/deletion, origin/authentication boundaries,
GET allowlist and signatures, disabled/wrong-broker connections, unknown identity,
partial-result retention, cooldown and in-flight invalidation. PostgreSQL CI
checks encrypted settings round-trip in isolation. Chromium checks mobile setup,
secret clearing, unknown proof, text-safe rendering, no localStorage and deletion.
Mocked transport and browser fixtures are NOT an authenticated DEGIRO test.
Only a subsequent successful owner-authorized provider connection can establish
real account compatibility; no such success is claimed by this implementation.
