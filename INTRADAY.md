# Bob intraday policy — 2026-10-05

## Previous rules (v1/v2; superseded by v3 below)

- 1h determines direction; 15m and 5m must confirm that same direction. Neutral is not confirmation. 4h is displayed as context, never a veto or a replacement for missing 1h data.
- A new direction requires two consecutive closed 5m candles. Refreshes do not count. Missing confirmation, invalid history and stale required data revoke entry eligibility.
- Recent 5m/15m/1h gaps block entry. The last closed 5m candle must have started no more than 10 minutes ago. Source times are preserved.
- Start parameters remain EMA 20/50/200, RSI 14, MACD 12/26/9, ATR 14. A 15m ADX below 20 blocks new signals. These are testable initial choices, not optimized or proven profitable settings.
- Zurich time, including DST: new signals Monday–Friday 08:00–21:30. At 21:45 the UI and enabled background trade notifications advise checking closure. This is Bob's strategy schedule, not an exchange/issuer calendar. Actual product trading hours remain an additional constraint. There is no automatic order execution.
- Existing structure/Fibonacci/ATR stops (default ATR multiplier 1.5), minimum reward/risk 2, no-loosening trailing rules, KO and product-evidence gates remain in effect. Stop and target now use a fixed validated 15m history, independently of the chart display (see entry-context review below).
- Contract-specific Future analysis now requires 1h/15m/5m; its historical quotes remain delayed. A fresh identified CFD remains the preferred current reference according to the already implemented reference policy. CFD quotes never fabricate historical candles. Reference accuracy validation is still required for conditional product candidates.
- Existing 15m/5m shadow comparison remains separate, preserving the running experiment and its old policy/version. Its results do not certify the new active policy. New active observations carry a separate rule version; historical observations remain stored and are not counted as evidence for the new active rules.

## Evidence and limits

Jin et al., “Performance of intraday technical trading in China’s gold market”, Journal of International Financial Markets, Institutions and Money (2022): https://www.sciencedirect.com/science/article/abs/pii/S1042443121001876 . The indexed abstract reports attractive in-sample rule performance disappearing with low transaction costs. This is evidence against assuming an indicator combination guarantees returns, not a direct calibration for DEGIRO products. The full article was not accessible in this session.

Fidelity indicator documentation: https://scs.fidelity.com/webcontent/ap010098-etf-content/18.05.0/help/research/learn_er_glossary_1.shtml describes 14-period ATR, including intraday use. Common defaults do not establish an optimal trading strategy.

The 1h/15m/5m hierarchy, ADX threshold, daily schedule, ATR multiplier and reward/risk threshold are engineering/strategy starting values. No source establishes them as an optimal gold strategy. Profitability requires out-of-sample assessment with actual executable product prices, fees, slippage and spread. The user's exclusion of spread from ranking is preserved; this does not justify ignoring spread when measuring realized profitability.

## Verification

Deterministic tests cover required timeframes, missing/opposed/neutral/stale evidence, optional 4h, Zurich cutoff and DST, Future frame eligibility, and one daily background reminder even when price data are unavailable. Existing dashboard and product-selection regression tests remain required. A live-market profitability or CFD-accuracy result is not implied by passing software tests.

The server now reads the tracked product module directly, eliminating the embedded duplicate so the tested and served versions match.

## Correctness review — 2026-10-06 (v2)

- Each historical 5m replay evaluates MTF freshness at that candle's close, rather than at the wall clock when the replay happens. This prevents a later reload from silently invalidating older confirmation evidence. Live freshness gates still apply.
- Flat RSI input returns 50 consistently in dashboard, server verification and partial backtest. Rising-only input remains 100; falling-only input remains 0.
- Stale or missing 5m data are rejected before the expensive multi-frame replay. No stale-entry threshold is relaxed.
- Audit v2 is separate from v1. Existing observations retain their version and remain stored. No profitability claim or parameter optimization follows from these correctness fixes.

## Entry context comparison — 2026-10-06

`entry-quality-v1` is an observational comparison, not a new entry permission. It records nearest confirmed 15m pivots plus observed Zurich-day ranges, 5m EMA20 distance in 5m ATR, confirmed-signal age, per-frame source age/gaps, and the existing 15m trend-strength value/change. Day ranges are explicitly partial observations. Calculations use the same technical closing-price history; they do not mix the current spot/CFD basis into historical distances.

Initial comparison thresholds: EMA20 distance <=1.5 ATR, room to the next obstacle >=2R (fixed 15m stop with multiplier 1.5), confirmed signal <=15 minutes old. Unknown obstacles/age fail the candidate only. These thresholds are unvalidated and do not change live direction, ranking, or push permissions.

Stop/target calculations now require fresh, valid 15m history (40 bars minimum, last 20 consecutive). ATR, structure and Fibonacci use this fixed source regardless of displayed timeframe. Missing 15m data yields no new suggestion; existing stops remain stored and no-loosening rules remain active.

The audit records paired 60-minute spot-direction results for the baseline and entry candidate. A filtered candidate has zero exposure. It reports mean directional change, hits, missed favorable moves, avoided unfavorable moves, and observed adverse excursion from archived spot ticks. Sparse ticks understate true extremes, so the display calls these observed values. Overlapping samples are not independent. No automatic tuning is performed. Product bid/ask comparisons remain separate; absent fees/slippage and execution records prevent a net-profit claim.

## Fast policy v3 (2026-10-06)

15m setup and 5m timing now determine direction; 1h/4h and EMA200 are context. One matching closed bar displays preparation; two remain required for a confirmed new direction. EMA20/50, MACD and RSI form one correlated collective. The existing strength calculation is DX, not Wilder ADX: the experimental filter accepts DX >=20, or rising DX >=15. No empirical superiority claimed. Weekday analysis no longer stops at 21:30; actual product market, quote, risk and evidence gates remain. No automatic closing or orders. Browser fallback rejects off-grid snapshots and inconsistent OHLC rather than retiming them. Missing or stale required candles still block.

Entry-quality thresholds (1.5 ATR / 2R / 15 minutes) remain a paired comparison and visible warning, not an unvalidated additional hard gate. Fixed 15m stops and targets remain. Audits isolate v3 from v1/v2. Existing trades and shadow experiments are retained.

Next-candle v1 is an experimental 5m continuation scenario from closed bars: close versus EMA20 and last close change must agree. The displayed band is plus/minus the last 14 mean high-low ranges, not a probability interval or predicted high/low. It includes a retrospective one-step check computed without the target bar; this is not a persisted live forecast track record. Invalid, stale, mixed, duplicate or gapped evidence is unavailable. No product approval derives from the scenario.

## Consistency audit v4 (2026-10-06)

- MTF now uses MACD(12,26,9) histogram, like closed-bar confirmation, rather than MACD slope. Server and browser are tested against identical histories. Invalid OHLC, missing timestamps, recent gaps, duplicate times and stale bars cannot confirm MTF.
- EMA200 stays context in secondary collective calculations and the trend block. Equal EMAs are neutral. RSI50 is neutral consistently; RSI14 starts with 15 closes. Missing/nonfinite collective inputs cannot create directional agreement; duplicates add no votes.
- Actual Wilder ADX14 is now calculated for the ADX display. The existing rolling DX14 remains separately named and retained for the fast filter and legacy shadow experiment; it is not silently replaced by a slower formula. ATR remains SMA14 of True Range (clearly labeled), including gaps; fixed 15m ATR controls product risk context and stop/target models.
- Product selection and background use full-precision 5m signal context plus fixed 15m ATR, never rounded DOM indicator values. Signal rendering refreshes the cached active status after computing the decision. Stale/invalid signal evidence neutralizes the current-analysis blocks.
- Market structure uses confirmed 3x3 swing highs/lows, not Bollinger position plus stochastic. Fibonacci candidates sort chronologically before range size, never mix candle indices with USD. Broken origin levels invalidate the swing. A passed extension is not reused as a forward target. Nonpositive stops/targets, unknown direction and wrong-side stops are rejected. ATR-capped stops disclose that the cap may lie inside structure.
- Flat Bollinger bands are displayed as no variation, not above band.

Defaults remain engineering/test settings, not calibrated probabilities or proof of profitability. New evidence is isolated under intraday-consistent-v4. Existing trades and prior audits remain stored.

Formula reference checked: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/DMI (Wilder smoothing, initial DX average and recursive ADX).

### Parameter inventory reviewed

| Parameter | Role / review result |
| --- | --- |
| EMA20/50; EMA200 | Fast trend collective; EMA200 context only, equality neutral |
| MACD12/26/9 | Histogram consistently used, no slope substitution |
| RSI14; 25/50/75 | Wilder RSI, neutral boundary at 50; outer bands describe extension, no independent vote |
| ATR14 | SMA True Range for dashboard/risk; fixed 15m risk basis; no direction vote |
| Wilder ADX14 / 25 | Corrected display and regime context, not a separate direction vote |
| Rolling DX14; 20 or rising >=15 | Existing fast filter retained as an experimental setting |
| 5m/15m; 1h/4h | Timing/setup; higher frames contextual, latest closed-bar freshness checked |
| 2 closes; 3-close comparison | Preparation after one, confirmation after two; legacy comparison preserved |
| 20-bar breakout; 0.15 ATR | Closed-bar breakout confirmation retained |
| 3x3 pivots; 180-bar Fibonacci | Chronological choice, broken origin invalidation, scale-independent pivot ranking |
| Fib 38.2/50/61.8/78.6; 127.2/161.8 | Arithmetic checked, context/targets, no added vote |
| Bollinger20/2; stochastic14/20/80 | Context only; flat-range boundary repaired |
| VWAP | Requires observed positive volume, no substitute volume and no added vote |
| Stop1.5 ATR, buffer0.2 ATR, cap max(2.5,mult+0.75) ATR | Positive/side validation, cap disclosed; existing stops not loosened |
| Target >=2R default | Correct-side positive target only; no expected-return claim |
| Quality1.5 ATR/2R/15min | Shadow comparison, no additional hard gate; not calibrated |
| Regime ATR%0.25/0.65 | Context on the same technical price basis, not mixed with spot |
| Next-candle EMA20 / mean14 range | Experimental scenario only, no probability or approval |

Passing formula and integration tests does not establish optimal settings or profitable live decisions. No thresholds were tuned on the validation fixtures.

## Responsive policy v5 (2026-10-06)

User requested removal of unnecessary intraday friction, including RSI25/75. This is a changed hypothesis, not an empirically proven improvement.

- Required active history: 100 closed bars (EMA50 warm-up); EMA200 requires 200 only for its optional display. Legacy shadow experiment retains its old 200-bar requirement.
- EMA20/50 and MACD histogram must agree. Price versus EMA20 and RSI above/below50 determine full or partial collective strength, without independently vetoing direction. RSI25/75 are extension warnings, never forced reversal or neutralization. Unknown/nonfinite inputs still fail.
- One strong closed 5m bar can confirm a new direction when the 15m setup agrees; weak strength, disagreement in supporting indicators or a new breakout requires two closes. No intrabar confirmation. Weak DX is a two-close requirement rather than permanent neutralization.
- Recent data recovery requires three consecutive closed bars on required frames rather than twenty. Older gaps are not filled and are not automatically declared market closures. Current data age, OHLC and duplicate checks remain. True Range still includes price gaps.
- Confirmed pivots use two neighbors each side instead of three; confirmation still waits for two following bars. This can detect more minor swings.
- Structure stops are no longer mechanically tightened inside structure by an ATR cap. Above-guideline distance is disclosed. Existing active stops retain their no-loosening protection. Minimum 2R remains a planning target, not a claim of achievable return; quality thresholds stay nonblocking comparison warnings.
- Browser, server, product context and background share the active policy. The old shadow remains frozen; audit observations use intraday-responsive-v5.

Trade-offs: shorter warm-up, fewer confirmation bars and faster pivots can increase noise and false signals; wider structure stops can require smaller size or make a product unsuitable. Live and out-of-sample evidence must establish whether this version is better.

## Prospective four-day comparison (v6)

Campaign gold-fast-cautious-20261006-v1 runs 6 October 2026 07:00 through 10 October 2026 07:00 Europe/Zurich (96 calendar hours). Weekend slots are excluded, outages are counted, and deployment/restart does not reset the dates or observations. There is no automatic adoption of a winner.

Fast: existing adaptive one strong / two weak closes. EMA20/50 distance below 0.1 of 5m ATR or MACD histogram magnitude below 0.02 ATR makes a bar weak; these fixed experimental margins are not fitted. Cautious: three consecutive closes of the same core direction, neutral immediately if the latest core direction does not agree. Both use identical source bars and freshness checks. Entry location is a separate prominent notice, not a new compulsory gate. Early pending direction is visible without claiming confirmation.

One independent, durable campaign runs from the server monitor even without push subscriptions. Capture the first poll within five minutes of each eligible hour; freeze it, including invalid data. Missing polls are reported as missing. Paired spot direction outcomes use the first actual stored Gold-API spot quote 60–61 minutes after capture; no estimated outcomes. Neutral means zero exposure. Report signal counts, hit/false-direction counts, flat, wait, mean gross directional movement per paired case, worst observed endpoint, observed adverse excursion (at least 54 sampled minutes), avoided unfavorable and missed favorable moves, and coverage. These are hourly signal observations, not filled trades or independent statistical trials; polling jitter can make adjacent horizons overlap slightly. No stop/target ordering, fees, slippage or product-return claim.

A descriptive leader is based on mean paired gross directional movement, with at least 20 pairs and 80% coverage required to label an end-of-window lead. This minimum is an operational threshold, not statistical significance or proof of general superiority. The endpoint and method stay fixed for the study. All raw campaign records and outcomes persist separately from rolling legacy audit history. Read at Lernen → Schnell oder vorsichtig · Vier Tage.


## Optional minute entry experiment v1 (2026-10-07)

The price chart supports 1m candles and lines, with the same timeframe-local confirmed-pivot Fibonacci retracements/extensions and saved overlay switches. Minute candles come only from the native XAUUSD OHLC feed; no reconstruction from 30-second spot samples or substitution with futures. Missing/stale data are disclosed. The extra request shares the existing bounded secondary-data deadline.

The optional minute-entry-v1 observation requires 100 closed valid minute bars, fresh source times (latest opening time at most two minutes old), three consecutive recent bars, XAU/USD identity, and the current confirmed 5m/15m direction. EMA20/50 and MACD collective, candle body and last-close change must support that direction. Otherwise the experimental candidate waits. Unavailable data are excluded, not scored as a successful filter. Main signals, stops, product ranking and pushes do not use this experiment.

Browser and background record the same helper result in the decision audit. Lernen shows a separate paired 60-minute spot-direction comparison: retained/filtered cases, mean gross directional movement, missed favorable and avoided unfavorable moves. The earliest valid observation per 5m decision is retained in reporting. This is an entry-filter comparison, not a simulation of a delayed fill. Existing four-day fast/cautious campaign is unchanged. No fees, slippage or product profit claim; a net-cost comparison still needs executable product data. No automatic adoption.


## Market-analysis audit — 2026-10-08

Reviewed main revision 3a726ec, dashboard math and presentation, server MTF,
shared headless worker, product collective, exact-contract analysis and existing
formula/confirmation/risk tests. This is a software and rule audit, not a live
profitability certification. Authenticated current indicator values were not read.

| Parameter | Finding / decision |
| --- | --- |
| EMA20/50, MACD12/26/9 | Core agreement; browser/server numerical parity tested. Retain. |
| RSI14, 50, 25/75 | Wilder smoothing; flat=50, rising=100, falling=0. Extreme RSI is an extension warning, not an automatic reversal. Retain. |
| EMA200, 1h/4h | Context only. Clarify market summary and narrative so context is not presented as active intraday direction. Future EMA200 unavailable below 200 bars. |
| Kollektiv | One correlated price family, not independent votes. Discrete outputs 0/25/50/75/100; 30/70 are display cutoffs, not probabilities. |
| 15m setup / 5m timing | Required alignment. One strong or two weak closes is the intentional responsive policy. Reversal hysteresis can retain an old direction while the raw score changes; this is disclosed, not a formula contradiction. Product collective separately checks current agreement. |
| Wilder ADX14 / rolling DX14 | Distinct formulas and roles. ADX display is smoothed; DX fast filter is experimental. Neither adds a directional vote. |
| ATR14 | Dashboard SMA True Range is explicitly documented; Future uses Wilder smoothing, now identified in output. Do not silently swap risk models. |
| Fibonacci / structure | Dashboard confirmed pivots and broken origins tested. Fix Future recent-gap/OHLC checks, broken-origin Fibonacci and broken final structure; suppress structure when 5m history is unavailable. |
| Bollinger20/2 / stochastic14 | Descriptive context only; flat ranges neutral. No case for extra directional weight. |
| VWAP | Loaded-window volume-weighted context, not exchange session VWAP. Native broker normalization has no volume, so n/v is correct. No synthetic volume; no reason to add a live gate. |
| Stops / targets | Fixed 15m basis, structural stops, no-loosening protection, 2R planning. Tests check direction and missing data. 2R is not expected profit. |
| 1m / next candle / entry quality | Experiments and warnings, not additional permissions. Preserve existing comparisons and their identities. |

No new indicator or optimized threshold adopted. Candidate simplification is to
keep Bollinger/stochastic/VWAP as optional context, as already implemented. A
session VWAP would require documented session boundaries and real suitable
volume; it is not available from current native candles. Any change to periods,
DX filters or confirmation counts needs a separate prospective/out-of-sample
comparison with executable bid/ask, costs and slippage. Spread remains excluded
from product ranking as requested, but execution cost must enter profit evaluation.

References consulted:
- Fidelity RSI: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/rsi (RSI can remain extreme during strong trends).
- Fidelity DMI: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/dmi (Wilder ADX smoothing and non-directional strength).
- Fidelity ATR: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr (True Range, Wilder smoothing, volatility not direction).
- Bailey et al., The Probability of Backtest Overfitting: https://escholarship.org/uc/item/4w1110bb (selection/overfitting risk; no calibration of Bob's parameters).
- Jin, Performance of intraday technical trading in China's gold market: https://www.sciencedirect.com/science/article/pii/S1042443121001876 (indexed material only; full paper not read; not evidence for an optimal Bob setting).
