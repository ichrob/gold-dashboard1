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

Each simulated account also includes its last five cases with recorded outcome flags,
model cost assumptions, charged fees/slippage and model net result when known. Unknown
net returns remain null; historical gross-only cases are not retrospectively re-priced.
When the response exceeds its size limit, the large journal is omitted first. Trade,
learning and repair details are retained if the remaining report fits; each omitted
section is named explicitly. A missing section is never evidence of feature health.

Original Gold-API input events also preserve their source-time/price pair in the
spot archive. Capture freshness is checked against the original event time, never
receipt time. Test evidence recovery can consult existing input events in the
original one-minute outcome window; different sources, stale-at-capture values,
conflicts and invalid starts remain excluded. This is not model interpolation.
Cases skipped by the bounded archive budget retain their queue position so later
passes eventually examine them.

## Durable diagnostic history and correlation

`simulationAndPush.history.areas.journal` reads a private PostgreSQL journal. Existing
server evaluations (including NEUTRAL and failed attempts), source input metadata,
background transport and Push outcomes share a source trace ID; each evaluator call
also has its own decision ID. Diagnostics never initiate an evaluator or send a Push.
The existing decision archive is also exposed through explicit projections so earlier
browser/background decisions remain distinguishable by origin and original timestamps.

The server health watcher records its existing observations every 30 seconds after its
90-second startup warmup. Journal records survive restarts once committed. A bounded
256-entry asynchronous delivery queue retries outages without blocking evaluation;
queue overflow/failure counters are visible and unflushed entries can be lost at shutdown.
Retention is seven days with a 60,000-event target; pruning runs every five minutes on
writes in bounded batches, so temporary excess is possible. A report returns the latest
20 entries of each stage, never the full unbounded archive. No backfill is invented.

Repair follow-ups compare the last 20 recorded recoveries against subsequent explicit
health evidence for the same fixed fault code. Repeated good observations over at least
five minutes with a check within two minutes yield `observed-stable`; a later bad check
is `recurred`. Missing/stale checks remain `pending-or-stale`. `recoveryKind` distinguishes
a verified worker restart from spontaneous recovery; this is temporal evidence, not
proof that a code change caused recovery. Builds and source/check timestamps are retained.
The journal write endpoint requires the existing internal service credential; ChatGPT
continues to have read-only diagnostic access, with no new account permissions.
