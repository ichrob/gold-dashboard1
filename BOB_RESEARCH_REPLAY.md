# Durable comparison evidence and reproducible research

No automatic age-based expiry applies to the original Spot observations,
product quote/case/cohort records, paired price comparisons, prediction/truth
records, decision audit (including its dependent outcomes), weekend observations,
Zukunft observations or derived trade price curves. Existing bounded read windows
remain unchanged. This does not recover observations deleted before deployment.
The database has finite capacity; diagnostics expose database/replay archive sizes.
No external backup or unlimited physical storage is implied by this policy.
Operational session/log cleanup and user-directed deletions are separate.

Accepted candle checkpoints also append deduplicated source-key/time/content
revisions to `bob_candle_evidence`. An updated checkpoint does not erase earlier
OHLC observations. Source disagreement is retained, not silently corrected.

Each new weekday strategy calculation freezes a compressed `bob-research-replay-v1`
package before publication. It includes the exact input rows (including source and
clock fields), prior learning report, checkpoint/day, cost assumption, expected
report, Python version, deployment commit and the source of the three pure research
modules. SHA-256 covers the complete uncompressed package. The package and report
are saved in the same PostgreSQL transaction with no automatic expiry; identical
packages are deduplicated. Read access alone performs no replay or code execution.
A saved package proves captured inputs, not market validity or profitable trading.

Retrieve a package through the existing authenticated POST `/strategy-lab/read`
using `{"replayId":"<64-character-id-from-report>"}` and the existing service-token
transport. Never paste a token into chat or public logs. The response contains the
compressed export under `replay`. With the matching reviewed code revision:

```
python research_replay.py exported-package.json
```

The command verifies integrity and installed engine source, recomputes all seven
strategies and the learning state without network access, and compares the whole
result. It rejects a different installed engine instead of executing archived code.
Use the recorded Git commit and Python version for older versions. The archived
source is available for manual review if that commit is no longer accessible.
Prior reports without a replay ID remain legacy, not retrospectively reproducible.
This exact replay protocol covers reference strategy research. Other comparisons
retain their evidence and versioned repository algorithms; their individual full
replay procedures are not certified by this strategy replay test.
