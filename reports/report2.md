# BTC Futures Backtest and Training Report

Generated: 2026-04-22 UTC  
Run directory: `reports/backtests/20260422T023011Z`  
Initial account balance: `$5,000.00`  
Instrument: BTC perpetual futures proxy data from `history/BTCUSD` plus fetched missing candles  
Primary decision timeframe: `4h`  
Execution timeframe: `15m`

This report is an offline historical paper-trading assessment. It is not live-capital validation and should not be treated as proof that the system is safe for live trading.

## Executive Summary

The current baseline system lost money over the historical test window. Starting with `$5,000`, the baseline profile ended at `$4,699.35` net after modeled fees and slippage, a loss of `$300.65` or `-6.01%`.

After training and parameter selection on the chronological 80% training slice, the selected profile was tested on the remaining 20% holdout period. The trained profile ended the holdout with `$5,010.88` net, a gain of `$10.88` or `+0.22%`. This is an improvement over the baseline and shows better drawdown control, but the out-of-sample edge is very small after costs.

Main conclusion: training improved risk behavior and trade frequency, but the holdout result is only marginally positive. The trained profile should be treated as weak evidence of robustness, not enough evidence for live capital.

## Data Coverage

Requested period:

- Start: `2025-01-01T00:00:00+00:00`
- End bound: `2026-04-02T00:00:00+00:00`
- Effective period: `2025-01-01T00:00:00+00:00` through `2026-04-01T23:45:00+00:00` for 15m execution bars

Loaded and fetched rows:

| Timeframe | Local Rows | Fetched Rows | Final Rows | First Timestamp | Last Timestamp | Gaps |
|---|---:|---:|---:|---|---|---:|
| 15m | 11,296 | 32,480 | 43,776 | 2025-01-01 00:00 UTC | 2026-04-01 23:45 UTC | 0 |
| 4h | 706 | 3,130 | 3,836 | 2024-07-01 16:00 UTC | 2026-04-01 20:00 UTC | 0 |
| 1d | 118 | 338 | 456 | 2025-01-01 00:00 UTC | 2026-04-01 00:00 UTC | 0 |

The 4h data begins before 2025 because the statistical modules need warm-up history, especially the HMM regime classifier.

No missing ranges, duplicate rows, fetch errors, or internal gaps were recorded in the final audit.

## Methodology

The backtest used the existing project pipeline:

- Historical candles loaded through `data.historical_loader.HistoricalDataLoader`.
- Historical statistical snapshots built through `backtesting.snapshot.HistoricalSnapshotBuilder`.
- Regime classification, trend, volatility, change-point, tail-risk, efficiency, correlation, and probability modules were run through the same statistical stack used by the live/paper system.
- Decisions were generated through `MockAgentLayer`, keeping the run deterministic and independent from external LLM APIs.
- Trades were opened only after the safety checks passed conviction, expected value, change-point halt, max positions, drawdown limits, and trade-spacing rules.
- Position sizing used BTC units calculated from account equity, stop distance, Kelly fraction, stability score, max risk per trade, and max leverage.
- 4h candles generated decisions; 15m candles were used for entry/exit simulation.
- Fees and slippage were modeled in net metrics. Gross metrics exclude these costs.

Command used:

```bash
venv/bin/python backtest.py --start 2025-01-01 --end 2026-04-01 --equity 5000 --fetch-missing --max-candidates 4
```

The training run used a chronological `80%` training and `20%` test split. In trade terms, the training phase covered 2025 trades, while the out-of-sample phase opened trades from `2026-01-01` through `2026-03-22`.

## Baseline Current Settings

Baseline profile:

| Parameter | Value |
|---|---:|
| Minimum conviction | 70 |
| Minimum EV | 0.005 |
| Stop loss | 2.00% |
| Take profit | 4.00% |
| Max risk per trade | 2.00% |
| Max daily loss | 5.00% |
| Max weekly loss | 10.00% |
| Max open positions | 1 |
| Max position duration | 24 hours |
| Max leverage | 5.0x |
| HMM training window | 1,000 candles |
| Monte Carlo paths | 10,000 |

Baseline performance:

| Metric | Gross | Net |
|---|---:|---:|
| Starting balance | $5,000.00 | $5,000.00 |
| Final balance | $4,751.99 | $4,699.35 |
| Total PnL | -$248.01 | -$300.65 |
| Total return | -4.96% | -6.01% |
| Trades | 6 | 6 |
| Wins / losses | 1 / 5 | 1 / 5 |
| Win rate | 16.67% | 16.67% |
| Average win | $131.93 | $122.96 |
| Average loss | -$75.99 | -$84.72 |
| Profit factor | 0.35 | 0.29 |
| Max drawdown | $322.69 | $323.37 |
| Max drawdown percent | 6.36% | 6.44% |
| Sharpe | -0.97 | -1.13 |
| Sortino | -0.14 | -0.16 |

Baseline trade behavior:

| Item | Result |
|---|---:|
| Long trades | 5 |
| Short trades | 1 |
| Stop-loss exits | 3 |
| Max-duration exits | 3 |
| Take-profit exits | 0 |
| Best net trade | +$122.96 |
| Worst net trade | -$109.98 |
| Median net trade | -$89.05 |
| Average holding time | 14.04 hours |

Assessment: the baseline configuration traded very little and was too permissive on the few trades it did take. It produced poor win rate, negative expectancy, and losses after transaction costs.

## Training Phase

The training process evaluated the baseline plus three safety-preserving candidate profiles. The tuner selected by net performance after fees and slippage. Candidate generation did not loosen the baseline safety controls; it only kept or tightened risk limits, conviction, EV, leverage, and max holding duration.

Selected trained profile:

| Parameter | Baseline | Selected |
|---|---:|---:|
| Minimum conviction | 70 | 80 |
| Minimum EV | 0.005 | 0.010 |
| Stop loss | 2.00% | 2.00% |
| Take profit | 4.00% | 4.00% |
| Max risk per trade | 2.00% | 0.50% |
| Max daily loss | 5.00% | 3.00% |
| Max weekly loss | 10.00% | 6.00% |
| Max open positions | 1 | 1 |
| Max position duration | 24 hours | 12 hours |
| Minimum time between trades | 4 hours | 4 hours |
| Max leverage | 5.0x | 2.0x |
| HMM training window | 1,000 | 1,000 |
| Monte Carlo paths | 10,000 | 10,000 |

The selected profile is meaningfully more conservative than the baseline:

- Higher conviction threshold: `70` to `80`.
- Higher expected-value threshold: `0.005` to `0.010`.
- Lower max risk per trade: `2.00%` to `0.50%`.
- Lower daily and weekly loss limits.
- Lower leverage cap: `5.0x` to `2.0x`.
- Shorter max position duration: `24h` to `12h`.

Training performance:

| Metric | Gross | Net |
|---|---:|---:|
| Starting balance | $5,000.00 | $5,000.00 |
| Final balance | $5,384.28 | $5,077.08 |
| Total PnL | $384.28 | $77.08 |
| Total return | 7.69% | 1.54% |
| Trades | 134 | 134 |
| Wins / losses | 75 / 59 | 65 / 69 |
| Win rate | 55.97% | 48.51% |
| Average win | $15.89 | $15.87 |
| Average loss | -$13.68 | -$13.84 |
| Profit factor | 1.48 | 1.08 |
| Max drawdown | $128.07 | $179.79 |
| Max drawdown percent | 2.54% | 3.60% |
| Sharpe | 1.85 | 0.36 |
| Sortino | 1.24 | 0.17 |

Training trade behavior:

| Item | Result |
|---|---:|
| Long trades | 63 |
| Short trades | 71 |
| Stop-loss exits | 21 |
| Take-profit exits | 6 |
| Max-duration exits | 107 |
| Best net trade | +$50.90 |
| Worst net trade | -$29.52 |
| Median net trade | -$0.27 |
| Average holding time | 11.13 hours |

Training assessment: the selected profile substantially reduced position size and drawdown. Gross performance looked strong, but fees and slippage consumed most of the edge. Net performance was still positive, but only modestly so.

## Out-of-Sample Test Phase

The out-of-sample phase used the selected trained profile on the holdout period. This is the most important part of the report because it was not used for parameter selection.

Out-of-sample performance:

| Metric | Gross | Net |
|---|---:|---:|
| Starting balance | $5,000.00 | $5,000.00 |
| Final balance | $5,101.94 | $5,010.88 |
| Total PnL | $101.94 | $10.88 |
| Total return | 2.04% | 0.22% |
| Trades | 40 | 40 |
| Wins / losses | 21 / 19 | 20 / 20 |
| Win rate | 52.50% | 50.00% |
| Average win | $14.01 | $12.39 |
| Average loss | -$10.12 | -$11.84 |
| Profit factor | 1.53 | 1.05 |
| Max drawdown | $78.06 | $91.39 |
| Max drawdown percent | 1.52% | 1.80% |
| Sharpe | 1.72 | 0.24 |
| Sortino | 1.39 | 0.11 |

Out-of-sample trade behavior:

| Item | Result |
|---|---:|
| Long trades | 18 |
| Short trades | 22 |
| Stop-loss exits | 4 |
| Take-profit exits | 1 |
| Max-duration exits | 35 |
| Best net trade | +$48.28 |
| Worst net trade | -$28.01 |
| Median net trade | -$0.55 |
| Average holding time | 11.00 hours |

Monthly out-of-sample net PnL:

| Month | Trades | Net PnL | Net Wins | Net Losses |
|---|---:|---:|---:|---:|
| 2026-01 | 22 | $51.74 | 11 | 11 |
| 2026-02 | 8 | -$10.99 | 4 | 4 |
| 2026-03 | 10 | -$29.87 | 5 | 5 |

Out-of-sample assessment: the trained profile avoided large drawdowns and ended slightly positive after costs. However, the net profit was only `$10.88` on a `$5,000` account, and the median net trade was negative. The system was barely above breakeven after transaction costs.

## Candidate Comparison

The training sweep evaluated four profiles:

| Candidate | Key Differences | Net PnL | Net Return | Net Win Rate | Net Profit Factor | Net Max DD |
|---|---|---:|---:|---:|---:|---:|
| candidate_000 | Baseline settings | -$300.65 | -6.01% | 16.67% | 0.29 | 6.44% |
| candidate_001 | Higher conviction/EV, lower risk/leverage, 12h max duration | $77.08 | 1.54% | 48.51% | 1.08 | 3.60% |
| candidate_002 | 1% stop, HMM window 750 | -$346.88 | -6.94% | 0.00% | 0.00 | 6.94% |
| candidate_003 | Lower risk/leverage, HMM window 750 | -$275.08 | -5.50% | 36.36% | 0.62 | 5.50% |

Candidate `001` was selected because it was the only candidate with positive net training performance and acceptable drawdown. It also preserved or tightened the safety settings relative to the baseline.

## Risk and Drawdown Observations

The selected trained profile improved risk control in several ways:

- Net max drawdown fell from `6.44%` in the baseline to `1.80%` on the out-of-sample test.
- The account did not approach insolvency or extreme leverage behavior.
- Position size was much smaller due to the `0.50%` max risk per trade and `2.0x` leverage cap.
- The system shifted from sparse baseline trading to more regular, smaller trades.

The main risk is not catastrophic loss in this run; it is lack of durable edge. After fees and slippage, the out-of-sample profit was only `$10.88`. Small changes in transaction costs, fills, spread, funding, or latency could erase the result.

## Interpretation

The baseline current settings were not acceptable on this historical sample. They produced low trade count, low win rate, negative PnL, and a negative risk-adjusted profile.

Training improved the system by tightening filters and risk limits. The trained profile produced a small positive out-of-sample net result with low drawdown. That is directionally better than the baseline, but the performance is too close to breakeven to infer a reliable trading edge.

The result is best described as:

- Baseline: failed this backtest.
- Trained profile: improved, conservative, and marginally profitable out-of-sample.
- Overall readiness: not sufficient for live capital without more validation.

## Limitations

Important limitations:

- This is still an offline simulation, not exchange-verified execution.
- The run models fees and slippage, but does not model every real futures cost such as funding rate, liquidity impact, rejected orders, or partial fills.
- The decision agent is the deterministic mock agent, not a real LLM agent.
- Only one major market period was tested.
- The selected profile was chosen from a small candidate set.
- The holdout period had only 40 trades, which is not enough to make a strong statistical claim.
- Net performance was very sensitive to transaction costs.

## Recommendations

Before considering any live deployment:

1. Expand validation to more historical regimes, including 2022, 2023, and 2024 if reliable 15m/4h/1d data is available.
2. Add funding-rate costs for BTC perpetual futures.
3. Run walk-forward validation with multiple rolling train/test splits instead of one static 80/20 split.
4. Increase candidate coverage, but keep all safety rules non-relaxed.
5. Compare mock-agent decisions with real-agent decisions in paper mode only.
6. Add exchange-realistic assumptions for spread, taker/maker fees, and order rejection.
7. Require materially positive out-of-sample net performance before any live-capital discussion.

## Artifact References

Full artifacts from this run:

- Summary: `reports/backtests/20260422T023011Z/summary.md`
- Metrics: `reports/backtests/20260422T023011Z/metrics.json`
- Trades: `reports/backtests/20260422T023011Z/trades.csv`
- Equity curve: `reports/backtests/20260422T023011Z/equity_curve.csv`
- Trained profile: `reports/backtests/20260422T023011Z/trained_profile.json`
- Data audit: `reports/backtests/20260422T023011Z/data_audit.json`

## Final Assessment

If the system had traded BTC perpetual futures with `$5,000` from `2025-01-01` through the available 2026 historical window, the untrained baseline would have ended at `$4,699.35` net.

After training on the first 80% of the sample and testing on the final 20%, the selected trained profile would have ended the out-of-sample test at `$5,010.88` net.

The trained profile is safer and better than the baseline in this run, but its net out-of-sample edge is very small. The correct operational conclusion is to continue paper validation and expand testing, not to treat the profile as live-ready.
