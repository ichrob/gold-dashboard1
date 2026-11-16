# Gold-API daily context service

The owner requested automatic historical collection and integration on 16 November 2026.
This service adds context to the existing Zukunft research view and read-only research diagnostics.
It never supplies candles, inputs to strategy fitting, live signals, product prices or orders.

## Collection and durability

Only the existing push service collects; no new paid Render worker or database.
It checks hourly and requests at most two records for the latest closed UTC weekday:
one daily average and one whole-day OHLC range. Two hours of settlement delay apply.
No historical backfill, synthetic weekends, minute/hour paid grouping or automatic retry.
Original validated responses are retained in the existing PostgreSQL database with
query day, mode, attempt/completion times and digest. About 520 small records per year
are expected. There is no deletion or replacement of historical evidence.

A transaction-scoped advisory lock protects a shared limit of eight attempts/hour
across replicas and a unique day/mode claim prevents repeats across restarts.
The reservation commits before HTTP and consumes quota even on failure or crash.
Failed/incomplete/stale data are shown explicitly. A failed day requires a separately
reviewed recovery; normal polling cannot silently retry it. Reads never call the provider.
The existing database backup policy applies; a new restore proof has not been performed.

## Activation and collector handoff

Deploy after CI. In bob-push-service only, configure these Render environment keys:

- GOLD_API_KEY: owner enters directly into Render; never in chat/source/logs.
- BOB_GOLD_API_DAILY_ENABLED=1
- BOB_GOLD_API_COLLECTOR=render-exclusive
- BOB_GOLD_API_SERVER_NOT_BEFORE: UTC epoch seconds at least one hour after the
  last handset/provider test, and no earlier than the agreed collector handoff.

After handoff, do not run handset historical probes or another account consumer.
The handset SQLite journal is not shared with PostgreSQL. Preserve its original
successful research data, but do not use it as an active collector.
The public spot feed needs no key and does not use the history allowance.

A new key in Render requires deployment before the process sees it. Verify both
stored records through the existing authenticated research view and diagnostics.
A configured environment or running thread alone is not an acceptance proof.
Disabling BOB_GOLD_API_DAILY_ENABLED prevents later cycles from requesting data.
A request already in flight can complete. Original data remain retained.

## Validation

Unit checks cover closed weekdays, settlement delay, safe configuration and handoff.
PostgreSQL CI checks parallel collectors, durable claims, failed-call accounting,
restart behavior, backward clocks, retained original JSON, derived context and stale status.
The earlier handset one-off tests verified actual authenticated daily and OHLC responses.
Production activation is pending secret entry, deploy and a stored-result acceptance check.
