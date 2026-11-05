# Timely recommendations and prospective validation

This change reduces avoidable handoff delays. It does not authorize broker
orders, increase personal risk, relax KO guards, or establish profitability.

- The headless evaluator reports the actual entry-plan block: analysis,
  source age, direction, late-entry protection, target obstacle, or risk-plan
  calculation. An unsuitable target cannot become a candidate plan.
- Advisory warning plans are prepared from checked original bars and a fresh
  spot observation. The dashboard shows Gold-reference stop/target levels,
  explicitly retaining product and entry confirmation requirements. No
  position size is inferred from dashboard defaults.
- Existing four-slot product work is harvested again after analysis. Three
  direction-matching products receive priority below active and overdue
  products; per-product minimum intervals and source validation are unchanged.
- Concurrent spot readers can immediately use an immutable, still-current
  primary observation or the separately checked standby. The provider lock
  still permits only one fetch. If no valid source exists at cold start,
  readers may wait for the existing fetch. No source clock is rewritten.
- A paper analysis can retry once against a newer complete queued snapshot
  when the result is unavailable or the source age exceeds 45 seconds. The
  snapshot is re-evaluated as a whole; missing history is never interpolated.
- Push diagnostics retain source, generation, analysis-request/completion,
  provider-start/duration and signed browser-receipt clocks. Analysis timing
  includes evaluator queue time. Browser receipt timing is server receipt of
  an acknowledgement, not proof of when Android displayed a notification.
- Existing paper ledgers gain a small prospective summary, not another worker
  or simulation. Calibration starts with the new instrumentation; validation
  uses entries beginning at least 24 hours later. Only closed, completely
  evidenced same-rule cases with original entry clocks and example-cost
  calculations qualify. Historical cases, data gaps, deferred settlements,
  incomplete proof and changed policies remain excluded. This summary never
  changes a rule or declares a winning strategy or actual net profit.

Operating limits remain: current issuer observations do not establish an
executable DEGIRO quote or account-specific purchase eligibility. Morning
identity evidence alone is insufficient for a current entry price. Provider
outages can still leave a decision unavailable. Personal capital and loss
limits must be explicitly supplied before personal position sizing is added.

Tests include bounded fresh-bundle retries, standby/primary concurrency,
priority fairness, raw-clock/privacy projection, preparation expiry and target
obstacles, and prospective cohort separation. Runtime timing and prospective
performance require future ordinary operation; no past result is backfilled.
