# Gold history fallback acceptance

This is a separate **manual research probe**, not an enabled automatic fallback.
The live price pipeline never imports `gold_fallback` and never mixes its rows
with biquote/XAUS. No new dependencies, services, subscriptions or orders.

## Evidence (2026-11-12)

- A source snapshot from biquote omitted the candle opening 2026-11-11 22:00 UTC
  (23:00 Europe/Zurich), while containing 21:00, 23:00 and 00:00 UTC bars.
  This is a missing timestamp, not proof of a provider outage. The authoritative
  biquote instrument session calendar has not been obtained. Calendars from
  other brokers or CME futures must not be applied as if they describe this feed.
- Twelve Data lists XAU/USD as a commodity trial symbol. Basic is limited to
  8 API credits/minute and 800/day; commodities are generally listed under Grow.
  Trial access is not proof of permanent free production/display entitlement.
- An authenticated Basic 8 account was verified on 2026-11-12 (800 daily / 8
  minutely credits). Its official API playground returned status=ok for XAU/USD
  interval=1h, timezone=utc, including the closed 2026-11-11 22:00 UTC candle
  when requesting 22:00 through 23:00 UTC. The current-hour probe also succeeded.
  This proves account-specific access at test time, not a backend deployment or
  unrestricted display/storage rights. No credentials or raw prices are published.
- The actual precious-metal metadata omits exchange_timezone. The fetch adapter
  now supplies its explicit UTC request context; imports without that context
  still fail closed. Conflicting metadata is never overridden.
- Alpha Vantage GOLD_SILVER_HISTORY supports daily/weekly/monthly, not hourly.

Sources:
https://support.twelvedata.com/en/articles/5335783-trial
https://twelvedata.com/exchanges/commodity?group=core
https://support.twelvedata.com/en/articles/5214728-getting-historical-data
https://www.alphavantage.co/documentation/#gold-silver-history
https://twelvedata.com/markets/300755/commodity/xau-usd
https://twelvedata.com/terms

## Controlled acceptance

Before setting `BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED=1`, record an account-specific
confirmation of free XAU/USD hourly history **and the intended usage rights**.
Configure `TWELVEDATA_API_KEY` only in the existing protected environment. Never
put keys in commands, git, logs, screenshots or chat. No key or an unconfirmed
entitlement produces a fixed status without network access. Demo keys fail closed.

Run one closed UTC-hour probe, e.g.:

    python gold_fallback.py --utc-hour-ms 1794434400000

The request spans one hour; the parser selects only the exact requested open
clock. A missing candle remains missing. It validates symbol, interval, UTC
metadata (or explicit UTC request context for the verified metal shape), duplicates,
positive finite OHLC, bounds and closed time. No redirects,
no retries, ten-second timeout, bounded response; exception URLs are never logged.
Output is a research observation, never a broker execution quote.

An explicit `--archive /persistent/path/research.sqlite` stores a separate
research archive. It is **not** automatically durable on Render's ephemeral
filesystem: use an approved persistent path or integrate with existing durable
storage before unattended operation. Do not create a second live candle database.
Identity is source + symbol + interval + UTC open time. Changed OHLC creates an
immutable content-hash revision; repeated identical observations update only the
last-seen clock. Absent volume stays NULL. Reads/cache policy, retention, scheduler,
durable distributed rate limits and revision selection need acceptance before
automation; this manual probe is deliberately not a background polling service.

## Remaining acceptance gates

1. Confirm source-specific sessions/holidays and exact candle timestamp convention.
2. Authenticated Basic access is proven in the provider playground. Confirm intended
   usage/display/storage rights and configure the backend secret before enabling.
3. Check overlap against a complete same-provider series; never splice foreign bars
   into the primary source's hole or retrospectively claim a simulated fill.
4. Validate durable storage, bounded request budgets and backoff before scheduling.

`market_review.frame_health` now exposes bounded gap evidence from its recent
three bars with UTC missing clocks, `sessionStatus=unverified`, and
`automaticBackfillAllowed=false`. Existing health states and trading gates are
unchanged. This makes the distinction inspectable rather than asserting a closure.
