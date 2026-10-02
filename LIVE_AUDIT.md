# GCZ26 live evidence export

After signing in to Bob, use **Live-Prüfdaten exportieren (48 Stunden)** in the
collection panel. `/api/collection-export` returns a JSON download through the
existing Bob authentication. The internal archive request keeps the existing
server token; no token or credentials are included in the export.

`audit.predictions` preserves each frozen price, source quote time, reference
time, first archive receipt and matched truth time. `audit.truths` preserves
observed GCZ26 values, their quote times and first archive receipt times.
`pairingStates` separates matched predictions, missing truth within five seconds,
truth received before the prediction, and candidates requiring inspection of
the one-use matching rule. These are retrospective diagnostics of retained
rows, not stored reasons for all rejected inputs.

Each type is bounded to the most recent 6,000 rows within the 48-hour archive.
`truncated=true` must be treated as an incomplete export. An archive version
without audit support or a storage outage returns 503, never an empty success.
The original source name/provider envelope and rejected input events were not
stored per event; the export states these limitations. It cannot reconstruct
missing provenance or certify future error bounds. Historical interpolated
backtests remain separate and must not be imported as live validation.

The collection panel now shows the actual future source, original quote time,
reference age, spot age, source error and next scheduled source attempt.
No observation time is replaced by the download or refresh time. Existing
sample, matching, freshness and approval limits are unchanged.

Verified SG issuer metadata is retained if the downstream quote adapter raises
an exception. Missing bid/ask, timestamps or permission still block eligibility;
issuer metadata alone is not a current executable quote.
