# Twelve Data: guarded free Basic research expansion

**Status:** implementation on a review branch, **not deployed or scheduled**.
The original `gold_fallback.py` single-hour probe and Bob's existing market
feed, DEGIRO product proofs, trade gates, and Android displays are untouched.

## Written support confirmation (2026-11-12)
Twelve Data confirmed Basic may be used for occasional automated XAU/USD
**1h** OHLC requests strictly for private **internal non-display** research,
8 credits/min and 800/day. Raw bars may be privately archived while the
Basic account remains active, and must be deleted within 30 days after
account closure/access ends. A private dashboard showing the bars **or derived
indicators** requires a paid plan. No paid plan is permitted for Bob.

A follow-up support request asks explicitly about 1min, 5min, 15min, 30min,
1day, CHF/EUR, EUR/CHF, USD/CHF, internal indicators and scheduling.
**Until written confirmation, these additional scopes are disabled.**
Technical availability or an HTTP 200 response is not a license.

## Research adapter
`twelve_research_extension.py` adds:
- Individual fail-closed permission flags for each symbol and timeframe.
- UTC, identity, closed-candle, finite OHLC, alignment, duplicate and bounded
  response checks; preserves originals and independent content-hash revisions.
- Local persistent SQLite credit ledger (max 7/minute, 700/day, lower than
  Basic ceilings). Requires **one exclusive worker** using the same durable
  ledger, controlled by `BOB_TWELVEDATA_SINGLE_WORKER_LOCK_CONFIRMED=1`.
  Multiple Render instances / ephemeral disks are **not safe** for budgets.
- Research-only EMA, MACD, RSI, ATR and spot-reference paper comparison,
  only for contiguous same-source private research observations.
- Explicit gaps with `sessionStatus=unverified`. No cross-provider
  reconstruction of an original bar, no simulated historical execution.
- Status-only CLI output; neither bars nor derived results are exposed to
  Bob's UI or public/private API endpoints.

## Configuration (only once permitted)
Set `TWELVEDATA_API_KEY` in secret backend environment; never in chat,
GitHub, URLs in logs or screenshots. `BOB_TWELVEDATA_FREE_ACCESS_CONFIRMED=1`
confirms the existing approved XAU/USD 1h internal scope.

After the provider answers affirmatively for each *individual* new scope,
an operator can set `BOB_TWELVEDATA_SCOPE_XAU_USD_5MIN=1` or the analogous
`BOB_TWELVEDATA_SCOPE_CHF_EUR_1H=1`. Do not set these preemptively.
`BOB_TWELVEDATA_SINGLE_WORKER_LOCK_CONFIRMED=1` requires actual exclusive
worker/centralized durable ledger verification first. A local SQLite file
on Render's ephemeral filesystem **does not qualify**.

Example manual test (after all guards are verified):

```sh
python twelve_research_extension.py --symbol XAU/USD --interval 1h \
  --start-utc "2026-11-11 22:00:00" --end-utc "2026-11-11 23:00:00" \
  --archive /verified-persistent-private-path/twelve-research.sqlite
```

Run `python -m unittest test_gold_fallback test_twelve_research_extension`
without API keys. There is no background scheduler, no paid activation,
no new live quote, no migration of existing historical data.

## Remaining deployment gates
1. Receive written Basic authorization for each additional timeframe/pair,
   and confirm private indicator calculation and retention rights.
2. Confirm timestamps, sessions, available depth and provider credit weights
   with bounded authenticated original requests per approved scope.
3. Select a single worker plus persistent encrypted/private archive/credit
   ledger with approved retention and deletion on access termination.
4. Integrate *internal* simulation comparisons only after validating
   historical overlapping series, sample counts and source provenance.
5. Run complete CI, inspect rollout health and publish no Twelve Data raw
   bars, derived values, or displays.

This module is opt-in research scaffolding, not a claim that the entire
production integration has been accepted or deployed.
