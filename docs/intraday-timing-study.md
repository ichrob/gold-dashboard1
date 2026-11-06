# Intraday timing comparison — frozen protocol 2026-11-06

This prospective study tests the owner's approved hypotheses without promoting them into live market approvals, product rankings or real orders. It runs from the existing paper worker after the normal ledgers commit, inside its own transaction. No new provider queries or worker threads. It does not retire or overwrite earlier studies.

## Fixed variants and scope

Eight variants, each for maximum holding durations 30, 180 and 300 minutes:

- `base5`: 5-minute confirmed breakout plus EMA, MACD and aligned available hour context.
- `fast3`, `control7`: the same rules, with 3- and 7-minute confirmation.
- `neutral5`: allows an available, neutral hour context, still rejects an opposed or missing context.
- `noema5`, `nomacd5`: omit exactly one extra indicator confirmation.
- `pullback5`: breakout, subsequent retest and then recovery past the intervening bar's extreme; all three bars must already be closed.
- `timestop5`: base5 plus an exit after one third of the horizon (10/60/100 minutes) if current progress is below 0.25 initial risk units.

These are reference-spot models, NOT a reproduction of Bob's complete main approval logic or a new DEGIRO-product portfolio. Existing issuer-quote entry/exit comparisons remain separate. The 5-minute arm is the study reference. Entry times and available trades differ across variants: report independent descriptive results, not paired-trade significance.

All intervals use one bounded series of 120 closed XAU/USD minute bars. Bucket origin is the UTC Unix epoch, including for seven-minute bars; it does not shift with a user visit. Features use 105 **minutes**, not 105 timeframe-specific bars: 20/50-minute EMA, 12/26/9-minute MACD, prior 15-minute breakout range and 14 common 5-minute true ranges. This avoids changing indicator lookbacks merely by changing confirmation duration. The hour context comes from the current evaluator and must remain available and supported by a recent closed original hourly bar.

Stops are 1.5 common ATR from the observed entry; the frozen target is three initial risk units beyond the breakout level. Reject entry if the remaining target distance is below 1.5 initial risk units. Never loosen the stop. Stops/targets execute only at later observed spot prices, including overshoot, not fabricated fills at the exact level. Same-observation entry/exit and overlapping positions per variant are prohibited. A stop within 15 minutes is counted as a descriptive false start.

Round-trip cost is the existing illustrative 0.16% reference-spot assumption. It is **not** actual broker fees, executable spread, leverage, KO loss or a verified product return. Worst net result and observed adverse movement are reported; unobserved extrema remain unknown. No claimed strategy winner or profitability.

## Data, missing observations and persistence

Original and modeled input streams run separately. The modeled stream may carry a prior closed minute close over at most two missing minutes in the 120-minute window, only within the trading session. It cannot repair malformed/conflicting/open/foreign-instrument/provider-mixed candles. No interpolation using later prices. Derived-input cases are labelled and their returns kept separate from original-input cases. Modeled runs without a missing input overlap the original stream and are not independent samples.

No stale quote starts a position. Missing source observations and worker gaps over 90 seconds terminate the affected case as inconclusive rather than manufacturing stop/target outcomes. Model source age is capped at 180 seconds and remains labelled; no new source timestamp is manufactured. Open cases survive restarts in a single small state row; completed/inconclusive cases have unique immutable IDs. Repeated worker clocks do nothing. Maximum one open case per arm, 200 starts per arm, 20 calendar days, then drain and require review. Stop opening at 21:45 Zurich; no weekend entries. No deletion of original cases or change to older simulations.

This is a frozen forward evaluation, no retrospective fitting or automatic parameter promotion. Correlated cases, costs, missing data, varying entry counts and modest sample sizes must be considered before deciding to alter main signals.

## Delay evidence and display

Existing operations/test overview shows all eight variants at the three durations, with the original and modeled streams separate. Display requires a recent worker timestamp; merely reading a saved report does not make the worker healthy.

Record first observed warning, first observed matching main confirmation in the same 15-minute episode, main blocking reason, source age and first available matching product ask. These are observed times, not reconstructed signal onset. Push readout uses the existing bounded seven-day delivery journal and matches original early-warning direction and signal-bar timestamp. Test/synthetic events are excluded. Provider acceptance, signed browser acknowledgement and Android tray display remain distinct; missing or truncated evidence is explicit. No new notifications are sent by this study.

Database tables: `bob_intraday_timing_state`, `bob_intraday_timing_cases`. UI report is an exact campaign state read, not a full case scan. Existing authentication and diagnostic admission remain.


## Revision v2 — confirmed reversals (2026-11-06)

30/180/300 minutes are **maximum** holding durations. All 48 arms close earlier on a confirmed opposite main signal with matching fresh original source evidence, or when two consecutive, post-entry closed bars of that arm's 3/5/7-minute timeframe agree in the opposite EMA and MACD direction. This local exit does not wait for hourly alignment or a new breakout. Neutral, unavailable or single-bar counter-moves alone do not reverse a position. Stops/targets retain priority; all fills still require a later valid spot observation, never a synthetic sale price.

An opposite entry is optional and independent: require its normal variant gates, a valid new target/stop, sufficient remaining reward/risk, an open session and a source observation strictly newer than the exit source. Do not close and reopen on the same cycle or source quote. A still-confirmed opposing main signal blocks an entry. Link eligible opposite entries within 30 minutes to the closed reversal case, with separate reversal-exit/re-entry counters. No guarantee of immediate re-entry.

Version v1 is preserved. Open v1 positions drain with the new exit protection explicitly labelled `exitPolicyChangedAt`; no new v1 entries. v2 starts independently only after v1 positions are closed/inconclusive, and cannot use a legacy exit quote for its first entry. Original v1 history and aggregate results are not pooled into v2.

These new arms still model Gold-Spot direction, not an actual product purchase. The existing product entry/exit comparison already exits on confirmed opposite main signals and validates product/quote/KO evidence for any later entry. No real-money order or broker automation is added.
