# Prospective entry opportunities, 12 November 2026

The older `entryExperiment` receives the final audit direction. If that is
neutral, all its threshold arms remain neutral. Preserve those historical
cohorts, but do not use them to claim that rejected opportunities were tested.

`entry-opportunities-v1` evaluates the worker's confirmed direction **before**
the timing and target gates create or reject its plan. It shares the original
timestamped bundle, learning policy, session, 15m structure stop and target
calculation. A missing genuine direction is still missing, not a fabricated
trade. The live gate and the 800/1,000/3,000/5,000 EUR ledgers are unchanged.

Six predeclared arms:

| Arm | EMA distance | Signal age | Additional change |
|---|---|---|---|
| reference | 1.5 ATR | 15 min | none |
| distance25 | 2.5 ATR | 15 min | none |
| age20 | 1.5 ATR | 20 min | none |
| combined | 2.5 ATR | 20 min | none |
| minute | 1.5 ATR | 15 min | divergence >0.8 ATR requires two closed, original, contiguous 1m candles after the 5m close, aligned beyond its range; current spot within 0.25 ATR of the last close |
| zones | 1.5 ATR | 15 min | cluster confirmed 2x2 pivots within 0.2 ATR; require two touches separated by at least three bars; retain the outer 40-bar boundary; two closes beyond a zone plus 0.2 ATR mark it broken |

The minute arm never changes source clocks or substitutes minute prices for the
original spot. The zones arm keeps the same stop and target; weak pivots may
stop blocking only in that named hypothesis. Both require all other timing,
source, confirmation and plan conditions. Existing fresh follow-through and
pullback exceptions remain the same in all arms.

One shared opportunity starts when at least one arm can enter. Arms enter at
the same observed spot, or explicitly skip. No simultaneous overlapping episode
and no re-entry on the same 5m signal. Exit is the first observed stop, target,
180-minute horizon or 21:45 Swiss session close. Sample gaps over 90 seconds
remain inconclusive, including a missed end-of-day exit. No interpolation or
guaranteed stop fill. All arms must finish or skip for a comparable pair.

Costs are a fixed 0.16% spot round trip assumption. Results include net R and
fixed-reference-capital percentage returns at max 1% risk and 65% exposure.
These are **not** actual EUR accounts, compounded returns, KO product profits
or executable DEGIRO fills. Both original source observations and assumed
valuation/costs are disclosed. Adverse/favorable excursions are sampled values,
not complete intrabar drawdowns. Individual closed counts and comparable-pair
returns are separate, so missing counterparts cannot inflate an apparent winner.

Persistence is one bounded campaign state, counters, one active episode and the
latest 20 complete/inconclusive episode details. This writes no additional raw
quote archive, uses no paid source and does not reset older study data. The
worker commits normal ledgers first; study errors have an isolated transaction.
The diagnostic `newStudiesBrief.entryOpportunities` shows worker timestamp,
six-arm blockers and counters, with winner/real-orders flags always false.

Acceptance: independent EMA oracle, LONG/SHORT symmetry, factorial interaction,
closed-minute evidence, zone strength, observed-price stop slippage and costs,
paired missing-data exclusion, idempotency, source-clock validation, persistence
and existing-account regression tests. Passing tests prove implementation behavior,
not profitable parameters. Forward observations begin only after deployment.
