# Gold-API historical XAU research (manual Free adapter)

Date: 13 November 2026. This branch does not enable historical Gold-API
fetching on the productive Bob backend. The existing 30-second Spot source
and research-only CHF/EUR parity shadow remain unchanged.

The provider allows a combined limit of **10/hour** across authenticated
/history and /ohlc. An API key is required in the **x-api-key** HTTP header.
Free /history supports groupBy=day/week/month/year; **minute/hour are paid**.
The /ohlc/XAU result summarizes a requested *whole range*: it is NOT
1m/5m/15m candle history. Official:
https://gold-api.com/llms.txt
https://gold-api.com/faqs
https://gold-api.com/pricing

This optional module only allows XAU/USD daily mean-price research or an
individual XAU/USD window's OHLC summary (up to 31 days). It cannot repair
intraday missing trading bars. Source results are kept separate from product
values, margin/KO evidence, live signals, push, and Android.

Security and zero-cost controls:
- Disabled by default. No imports on any production path, no scheduled job,
  no API route, no auto-retry, no account creation or subscription change.
- The operator must have the *already owned* free Gold-API key securely
  available as GOLD_API_KEY (never in GitHub, logs, chat or request URL).
- BOB_GOLD_API_FREE_HISTORY_ENABLED=1 and
  BOB_GOLD_API_EXCLUSIVE_ACCOUNT_CONFIRMED=1 require separate affirmative
  verification that this is the only consumer of the same free account.
- Persistent private SQLite journal mode 0600 required. Never use /tmp,
  GitHub runner checkout, or ephemeral Render filesystem. SQLite protects
  concurrency only on this same filesystem, not distinct machines. There
  must not be a second device/backend using the same key.
- Shared local safety budget is **8/hour**, retaining 2 calls of headroom
  for unknown provider-side accounting. Still respect the provider's 10/h
  account-wide quota; this journal does not know about other clients.
  A failed/uncertain HTTP attempt consumes the local reservation; no retry.
- Only closed timestamp windows; daily group always whole UTC days; no
  synthetic weekend or missing days manufactured. Bad source schemas,
  non-monotonic dates, invalid OHLC or mismatched query windows fail closed.
- Original response with provenance is stored locally for manual, internal
  research; no new database/Drive service or automatic archive maintenance.
  Separate retention, backup, migration and privacy review precedes any
  routine data collection.

Suggested future manual one-off invocation, only after operator has a free
API key, an OS-encrypted private persistent volume, and confirmed account
exclusivity:

    python gold_api_history_research.py --mode history-day --start 1794441600 --end 1794528000 --archive /private/persistent/gold-api-research.sqlite

The program prints status, row count and a short digest only; no API key,
raw historical prices, DB URI, trading action or personal data.

Offline no-network tests:
    python -m unittest -v test_gold_api_history_research.py

Release gate: test + GitHub CI; verify a single authenticated no-cost call
and provider's actual response format/timezone. Until that succeeds, this
module is a prepared integration, not a working live historical feed.
