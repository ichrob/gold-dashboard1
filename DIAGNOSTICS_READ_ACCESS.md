# Private operational diagnostics

The existing POST /mcp transport now supports `bob_diagnostics`, in addition to the two product tools. It reads cached market inputs, background heartbeat, collection status, research progress, paper-account heartbeat, push monitor counts and the sanitized problem index. Each observation retains its original timestamp when available; `observedAt` only marks report collection. Missing data is unavailable, stale market caches remain stale, and push monitor counts do not prove delivery. Reports do not assess forecast quality or authorize trading.

## Authorization and rollout

Both scanner and push-service revisions must include this change. The push-service `/diagnostics` route requires its existing internal credential and executes a read-only database transaction. No diagnostic data is added to public health endpoints.

Existing OAuth grants, including legacy persisted grants without a scope field, retain `bob:products:read`. Their refresh tokens cannot gain permissions. To access diagnostics, reconnect through the existing ChatGPT OAuth connection with `bob:products:read bob:diagnostics:read` and approve the updated consent page. A diagnostics-only grant cannot call product tools. Existing machine keys and legacy Basic authentication remain product-only.

The plugin's existing connection must refresh its discovered scopes and tools. Do not recreate the plugin or copy credentials into chat. Validate the deployed revision and make an authenticated `bob_diagnostics` call after reconnection. Until that call succeeds, report end-to-end verification as pending.

## Verification

`python -m unittest test_bob_mcp test_bob_diagnostics -q`

Tests cover old-grant preservation, refresh scope escalation rejection, new scope exchange and rotation, consent text, HTTP scope enforcement, bounded/no-secret summaries, missing/stale evidence, fixed tool arguments, and SELECT-only push snapshot reads.

## Expanded observations (schema 2)

The same authorized diagnostic tool now includes bounded product gaps and source recovery,
actual evaluator decisions and indicators captured passively after existing evaluations,
per-timeframe candle integrity, collection cadence, session mode, account balances and
simulated cost totals, stored trade monitoring/events, push observations, strategy learning,
video transcript coverage and saved media processing status, and durable repair event codes.
Database readers use SELECT inside savepoints in the existing read-only transaction;
a missing optional table becomes unavailable without hiding other observations.
There are at most 10 trade/subscription records, 20 events, 3 learning reports and 10 video
media records. Projection lists are capped at 20 and strings at 300 characters. Credentials,
subscription endpoints, raw transcripts, documents and arbitrary nested payloads are omitted.

Analysis capture is process-local and empty after restart until a normal evaluation runs.
Persisted monitoring evidence is separately timestamped. Epoch seconds are used for capture/cache
times; candle open times remain epoch milliseconds; database times are ISO timestamps.
A cache older than 120 seconds is flagged, but the reader must compare this with the scheduled
collection interval and session mode before diagnosing a stalled worker. Market closure and
broker-session pauses are distinct. Delivery history does not prove arrival on the handset.
Stored research summaries/frames do not prove that all videos were analyzed. Paper balances
are simulations, and learning evidence does not establish validated executable product returns.
The report performs no evaluations, repairs, notifications, orders or rule changes.
