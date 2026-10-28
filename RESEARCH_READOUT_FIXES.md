# Stored research access and chronology fixes

The `bob_diagnostics` research focus now has a dedicated authenticated reader.
It reads the latest saved strategy report instead of depending on the fast
current-day paper simulation response, which intentionally omits stored research.
The normal live/simulation/source readers are unchanged.

The internal GET `/research-status` requires the existing push-service credential.
Report admission occurs before borrowing a database connection. Its transaction
is read-only, uses a 1500 ms statement timeout and one latest-row SELECT.
Stored original timestamps and allowlisted research fields are preserved.
Empty storage and failed reads remain different states. This path does not run
workers, initialize tables, fetch prices, recompute strategies or export raw
replay packages. Existing OAuth diagnostics consent is still required by MCP;
merely installing a research callback cannot grant access.

Two research calculation corrections are intentionally versioned separately:

- `zukunft-walkforward-v3-latest12` selects the latest twelve complete folds on
  the existing chronological grid, instead of stopping after the first twelve.
  Training remains expanding and both four-bar purge gaps remain unchanged.
  The report exposes available/selected/omitted window counts and the latest
  evaluated/source timestamps. Unused incomplete tail bars remain unevaluated.
- `bob-rolling-shadow-v3-latest12` archives the previous protocol's proposal and
  prospective counters before starting a separate research cycle. Old and new
  counters are not pooled. Historical report revisions and their replay packages
  remain available under their original protocols. Replay of older packages
  requires the matching reviewed code, as before.
- `newIndependentEvidence` is true only when this invocation actually accepts a
  subsequent frozen-candidate observation. Repeating the same closed-bar input,
  or blocking it for a protocol/source mismatch, cannot inherit today's flag
  from a previous invocation. An observation is not proof of an independent
  broker trade, profitability or a new final holdout.

No live signal, stop, risk, knock-out, product approval or push policy changes.
No automatic promotion, deployment or real order. These simplified reference
strategies do not replace the separately frozen private five-topic study baseline.
Repeated windows across reports must still not be added as independent evidence.

## Validation

`test_research_access_fixes` exercises the actual internal handler, admission,
MCP scope boundary and focused server reader with synthetic observations. It also
contains a PostgreSQL integration test requiring `BOB_TEST_DATABASE_URL`; an
unavailable database must be reported as skipped, never passed.

`test_research_evidence_fixes` covers same-day retries, later same-day windows,
blocked protocol evidence, protocol migration, latest-window completeness and
the invariance of an earlier shared fold when later bars arrive. Candle fixtures
are fictitious. These tests are not historical financial backtests.

Targeted regression command:

```
PYTHONDONTWRITEBYTECODE=1 python -m unittest test_research_access_fixes test_research_evidence_fixes test_research_readout test_research_learning test_research_replay test_research_revision_storage test_research_self_review test_strategy_lab test_strategy_lab_daily test_strategy_lab_endpoint test_report_admission test_bob_mcp test_bob_diagnostic_focus_truth
```

After an explicitly authorized release, verify the deployed revision, then read
`bob_diagnostics` with `focus=research`. Confirm the original saved report clock,
its actual protocol and honest empty/unavailable states. A successful code test
does not establish production DB connectivity, export availability or DEGIRO
net performance.
