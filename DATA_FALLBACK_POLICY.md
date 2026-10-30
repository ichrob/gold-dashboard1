# Bob-wide data continuity

All consumers must use the shared source adapters, keep original source clocks,
and apply their own freshness and evidence gates. A successful fetch is not
proof of a fresh quote. Never renew a quote by changing its timestamp.

Selection order is a valid original observation, a validated alternate source,
then a clearly labelled calculation where a supported model and inputs exist.
If no admissible value exists, expose unavailable/stale with its reason. This
policy is not a promise that every datum has a substitute or zero latency.

## Shared paths

| Data | Shared path and recovery | Limits |
| --- | --- | --- |
| XAU/USD | `spot_data.current`: Gold-API, then background-warmed `xaus_spot.peek` | Original clocks, <=60 seconds; XAUS stays XAUS |
| USD/EUR, USD/CHF | `sg_quotes.market_input('fx')`, used by models and live bundle; `fx_data` primary plus warmed dated biquote midpoint backup | Indicative conversion, not an executable quote; source time, not fetch time |
| 1m/5m/15m/30m/1h/4h candles | Shared retained histories, native alternate history and complete lower-timeframe aggregation | No invented minutes, no mixed-provider or incomplete OHLC; 1m cannot be derived from larger bars |
| Indicators and signals | Existing evaluators derive outputs from the shared bundle | Existing minimum history, freshness and strategy gates remain |
| Product quotes and leverage | Existing issuer/alternate caches and `quote_updates`; validated hybrid anchors and product models | Correct ISIN/terms; computed reference values stay labelled and cannot become executable broker evidence |
| Futures | Existing exact-contract source plus separately calibrated spot/CFD models | A provider-specific model must reject a different proxy identity until supported/calibrated |
| Research and simulation history | Persisted observations and reproducible computations | No retrospective fabricated fills or results |
| Account, KO, product terms and trade execution | Authoritative observations only | Never infer an actual holding, fill, active KO status or missing contract terms from a market model |

`market_recovery` warms source adapters with bounded pending work and provider
caches/backoff. Shared spot/FX alternate readers do not wait for their refresh
lock or issue a new request. Source retrieval and downstream publication still
have finite latency. All six candle timeframes bypass an extra live-bundle TTL
when the recovery cache contains newer confirmed data.

Every new data consumer should reuse these paths and carry source, source time,
calculation status, input times and failure reason as applicable. Do not silently
introduce an independent cache or substitute a different instrument.
