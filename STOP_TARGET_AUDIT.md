# Stop and target evaluation

Newly inserted decisions with a valid saved Gold reference plan and a source
quote no older than 60 seconds register an immutable four-hour test. The test
starts at decision capture, never at a retrospectively selected favorable quote.
Equal rule/bar/plan levels from browser and worker share a test; changes to
entry, stop or target produce separate plan versions, not claimed trades.
Previously stored decisions are not backfilled into this new test.

The original entry, stop, target, direction, unit, ISIN (if available), decision
reference and rule version are retained. Source quote observations are examined
in time order. The first observed stop or target closes the test; later favorable
quotes cannot replace a stop. Gaps over 90 seconds before that event produce an
inconclusive result. After four hours without a hit, missing coverage remains
inconclusive; otherwise the result is no observed hit. Future/pre-plan quotes,
invalid prices and conflicting quotes never become evidence of a favorable hit.

These are observed Gold model tests, not continuous tick reconstruction, orders,
executed stop fills, product returns or net profit after fees. Price movements
between observations remain unknown. Profit stops beyond original entry, dynamic
trailing stops and extended targets need a separate lifecycle review and are not
misrepresented as original valid initial plans here.

Outcomes and test metadata persist with the decision's existing 30-day retention,
independent of the underlying seven-day spot archive. Interactive reports are
read-only. Workers evaluate up to 20 pending tests per batch; latest check time
is visible. Tagesprüfung displays all-day status counts and the first 100 details,
explicitly marking longer detail lists. Plan versions are not independent trades
or a trading success rate.

Validation: long/short first-hit ordering, gaps, expiry/open tests, out-of-window
and conflicting quotes, stale plan exclusion, immutable deduplication and
read-only report behavior are covered by test_stop_target_audit.py.
