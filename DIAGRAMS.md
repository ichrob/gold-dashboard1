# Diagramme under Mehr

Eight read-only sections share the authenticated audit reports: title alternatives,
ranking optimization, paper capital, drawdown, price accuracy, fixed-plan exits,
entry regimes/direction, and forward signal quality. No orders or new selection
rules are issued by the charts.

- Paper accounts use at most 366 stored daily valuations, not invented intraday
  equity. Euro P/L and percent since each account's own initial capital are separate.
  Daily sampled drawdown differs from the cumulative maximum observed by the worker.
  Unvalued days break the curve; missing quotes can conceal deeper drawdowns.
- Original/model price points are partitioned by the existing full learning identity
  (ISIN, currency, source, terms and scope). Store at most 720 observations per state,
  expose the newest 240 for each of the newest 24 states. A corrected chart point
  uses the candidate frozen BEFORE observing that point, never its subsequent fit.
  Training points and revoked leases have no corrected value. Chart MAE uses the
  original quote as denominator on exactly the paired observations; the learner's
  existing acceptance metric and thresholds remain unchanged.
- New lifecycle captures also freeze a separate original-stop/original-target case.
  It retains shared source, gap, KO and time safeguards and has no adaptive trailing,
  partial profit or reversal exits. Quotes continue until BOTH paths end. Legacy
  captures have no retroactive fixed path. A stop comparison requires complete
  evidence for both paths and all original candidate products. Return denominator
  remains EUR 100 including unallocated cash. Giveback is the positive observed
  peak profit minus the remaining positive exit profit, not an executable peak fill.
- Regimes come from frozen entry labels, split by currency and LONG/SHORT. Results
  are descriptive. Signal hit rate and mean directional gold movement use the same
  evaluated cases per horizon; missing and neutral counts remain visible.
- Missing data never becomes zero return. Accessible value tables accompany curves.
  Currency/horizon controls continue to apply to title, exit and regime comparisons.
  Account data uses a bounded read-only endpoint without loading case histories.

Validation: JS transformations/rendering tests cover gaps, missing values, currency
isolation and stale/empty states. Python tests cover frozen correction timing,
fixed-plan continuation after Bob exits, quote failure, target exits and bounded
read-only portfolio reporting. Existing PostgreSQL lifecycle integration also
covers persisted captures, restart and immutable entry. These tests establish
software behavior, not market accuracy or profitable future trading.
