# DEGIRO quote feasibility probe

This implements the read-only portion of the proposed app/backend bridge using
Bob's existing pinned `degiro-connector==3.0.36`, private authentication and
isolated worker. No second FastAPI server, shared frontend API password, paid
service, automatic polling job or order route is introduced.

## What the source inspection establishes

The pinned SDK has separate trading and Quotecast modules. Its documented
`BidPrice` / `AskPrice` metrics can be requested for an exact `vwdId`. Portfolio
valuation and chart `LastPrice` are not substitutes for these metrics. The SDK's
MetricType has no documented per-side bid/ask source timestamps. `LastDate` and
`LastTime` describe the last trade; response time describes receipt. Neither is
used to invent bid/ask source clocks. A successful sample therefore remains a
research observation, not a verified current executable broker price.

Sources inspected 2026-11-11:
- https://github.com/Chavithra/degiro-connector (Quotecast documentation)
- PyPI wheel `degiro_connector-3.0.36-py3-none-any.whl`: metric.py,
  ticker_fetcher.py, ticker_to_metric_list.py and constants/urls.py.
- https://www.degiro.ch/helpdesk/de/handelsplattform/verwendung-der-handelsplattform/kann-ich-mit-degiro-automatisierte-trades-oder
  (DEGIRO states third-party automation violates its terms; this implementation
  does not establish provider approval.)

## Manual private test after deployment

`POST /api/degiro/quote-test` uses the existing Bob login and same-origin check.
The private DEGIRO panel now includes a manual quote-test button. The request accepts only `otp` (optional six digits) and `quoteRequest`:

```json
{
  "quoteRequest": {
    "productId": "123",
    "isin": "US0378331005",
    "currency": "EUR",
    "exchangeId": "456"
  }
}
```

The example is synthetic, not a valid product mapping or a suggested test order.
For an explicit mapping, obtain all four fields from the same private original broker listing. Alternatively send only `isin` and `currency`: the probe performs one exact lookup (limit 20), rejects truncated or ambiguous results, and requires product-info confirmation of the sole matching product and exchange. There is no first-search-result fallback. Product info must match every field and supply
an `issueid` mapping; `vwdkey` and unknown mappings are explicitly unsupported.
Do not put a real private product list, credentials, OTP, client ID or session
ID into public issues, command arguments or logs. Existing credentials remain
in the backend environment. No credentials are accepted in this HTTP payload.

The test shares the one-off reader's lock and 60-second cooldown, refuses an
active sync session at the HTTP boundary, and has a 45-second subprocess limit.
After login and product identity validation it makes at most three quote polls.
A separate HTTPS host/path allowlist disallows orders, redirects and arbitrary
hosts. It unsubscribes on poll exit and logs out in the worker cleanup. SDK logs
are suppressed. A transport/auth failure is not retried through an alternate
host. Unavailable/rejected/session-reset protocol messages invalidate the sample.

The private response includes numeric bid/ask observations and their separate
reception times, but `bidSourceAt` / `askSourceAt` stay null and
`sourceTimesVerified`, `delayVerified`, `isExecutableQuote`, `tradeApproved`,
`liveOrdersEnabled` stay false. A fresh heartbeat does not refresh an old side.
`ok=true` means only that a two-sided observation was received. `lastQuoteTest`
is a separate process-local, sanitized diagnostic receipt; it does not overwrite
`lastConnectionTest` or persist across service restarts. No data enters ranking,
trade approvals or paper performance accounting from this test.

## Acceptance and remaining work

Local tests use synthetic identity/protocol frames and the real pinned SDK
parser. They establish input validation, partial updates, invalidation, no-order
transport boundaries, parent redaction and private HTTP controls. They do not
establish successful live login, gold-product availability, provider entitlement,
market delay, original bid/ask clocks or actual executability.

Before calling this a working feed, obtain a private live sample for an exact
broker listing and compare with its displayed venue/currency/quotes. A provider
source-clock and delay proof remains necessary even if that test succeeds.
No real order is needed or permitted to perform this test. If login, mapping or
subscription fails, preserve the fixed failure code and investigate that stage;
do not weaken the evidence rules or move the sample into the simulation feed.

## Authentication failure evidence

`BOB_AUTH_DENIED` reports fixed reasons only (missing cookie, unknown/expired
session, credential-version change, rejected persistent session, invalid session
state). Each reason is limited to once per minute. It contains no cookie,
username, password, token, path or request payload. Authorization decisions,
8-hour/7-day durations and store-outage 503 behavior are unchanged. This is
cause instrumentation, not a claim that the observed session loss is repaired.
