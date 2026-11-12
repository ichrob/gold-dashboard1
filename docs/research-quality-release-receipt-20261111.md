# Bob Research Quality Release Receipt — 11 November 2026

## Change already tested
Pull request #1539, full Bob CI, Risk, CodeQL Python and JS, and repair-evidence checks all succeeded on the identical commit `f2b7358a61be0b0fd6cd703345a6c303034b6e67`.

The change is paper-only: one transient invalid original sample no longer irreversibly poisons a one-hour original study if actual source observations recover within the existing 90-second limit; longer gaps still remain inconclusive. Every original invalid sample is recorded; no imaginary quote, trade, stop or exit is allowed. The 28 rapid research configurations (four setups and seven lever levels) are now represented in the read-only diagnostic projection.

## Operational publication
A GitHub ref fast-forward preserved test results but did not result in an observable Render build/deploy on either bob-private-scanner or bob-push-service by the last checked read-only report. This documentation-only GitHub Contents commit requests an ordinary main push and maintains fail-closed `checksPass` auto-deploy; it does **not** authorize or trigger an unverified manual deploy.

Do not close a deployment task until both Render services report the released commit as `live`, the latest original study tick occurs during an actual trading session, and read-only diagnostics show 28 rapid configurations. Previously stored inconclusive cases are not recalculated or rewritten.
