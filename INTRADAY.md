# Bob intraday policy — 2026-10-05

## Active rules

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
