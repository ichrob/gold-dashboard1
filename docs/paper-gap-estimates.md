# Simulation with estimated inputs

User-authorized policy, 6 November 2026: include calculated values when original
inputs are unavailable, visibly distinguish them from original observations.

The running quality campaign now persists a prospective `modeledSimulation`
beside its unchanged original-only run. Both use the observed signal directions,
same delays, 60-minute horizon and 0.16% assumed round-trip spot costs. They are
spot comparisons, not KO product fills. The companion starts on its first worker
cycle and keeps the campaign's existing deadline; it does not rewrite old cases.

`paper-gap-carry-v1` rules:

- Prefer the exact original input. Estimated inputs never set `verified=true`.
- With a current original spot and ready analysis, a missing closed 5m/15m
  analysis candle can use the preceding original close, at most two intervals
  back. O/H/L/C are equal model assumptions; actual extremes remain unknown.
  Provider-open candles, future candles and unanchored gaps are not filled.
- An existing scenario can carry the last verified spot for at most 180 seconds
  in the same Swiss trading session. Store original anchor and calculation time;
  an estimate cannot anchor another estimate or open a new delayed entry.
- Worker/source interruptions up to five minutes may keep a fixed-horizon
  comparison alive with `estimatedUsed` and an unknown intragap path. Longer or
  session-crossing interruptions remain inconclusive. Modeled points never
  assert observed stop/target hits. No KO or issuer evidence is manufactured.
- Closed companion cases have distinct `:model-v1` IDs and explicit model flags.
  Report their counts and returns separately, including how many used estimates.
  No automatic strategy promotion or real orders.

Existing retrospective `gap-model-v1` interpolation remains separate. Its
bracketing original observations must be at most five minutes apart and no later
than calculation time. A new 60-minute discovery lane uses 16 of the existing
32 recent-discovery slots; the other 16 retain the 15-minute lane. The existing
128-row historical discovery cursor and 24-row model budget remain bounded.
Original recovery remains first choice. Models are frozen, and later originals
are compared rather than replacing the saved estimate.

The read-only recent-followup diagnostic distinguishes an open original time
window, original quote awaiting processing, stored estimate, pending model and
missing model anchors. It inspects at most eight missing outcomes among the
latest 100 decisions. It does not itself calculate, write or repair evidence.
