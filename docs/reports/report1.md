# BTC Historical Backtest and Training Report

Generated from offline backtest run: `reports/backtests/20260421T200829Z`

This report evaluates the current BTC futures trading system as an offline historical paper-trading simulation. It is not evidence that the system is safe for live capital. The result shows severe risk-control and sizing failures under the current pipeline assumptions.

## 1. Executive Summary

The system was tested with a starting balance of `$5,000` over the requested period from `2025-01-01` through `2026-04-01` UTC. Local historical files were used first, and missing candles were fetched to fill the full requested range. The run used the current default pipeline: 4H statistical decision cadence, deterministic mock agents, Python safety/execution semantics, 15m candles for intraperiod execution checks, and no live LLM calls.

The baseline system produced one trade and lost far more than the starting balance. The training phase did not find any parameter candidate that satisfied the minimum acceptance criteria of at least 10 closed training trades and less than 25% max drawdown. The selected trained profile was therefore only a fallback, not a valid optimized model. Its out-of-sample result was also deeply negative.

The central finding is that the system is not currently suitable for paper-to-live validation without fixing risk sizing and account-level solvency controls. The reported negative balances are not acceptable trading outcomes; they indicate that the current paper execution sizing semantics can create exposure far larger than a `$5,000` futures account can support.

## 2. Run Configuration

Command executed:

```bash
venv/bin/python backtest.py --start 2025-01-01 --end auto --equity 5000 --history-dir history/BTCUSD --fetch-missing --train-split 0.8 --tune all --report-dir reports/backtests
```

Core settings:

| Item | Value |
|---|---:|
| Starting balance | `$5,000` |
| Requested evaluation start | `2025-01-01T00:00:00+00:00` |
| Effective evaluation start | `2025-01-01T00:00:00+00:00` |
| Effective evaluation end | `2026-04-01T00:00:00+00:00` |
| Decision timeframe | `4h` |
| Execution detail timeframe | `15m` |
| Train/test split | Chronological `80% / 20%` |
| Agent layer | `MockAgentLayer` |
| Gross result | Current paper execution assumptions |
| Net result | Gross result adjusted by `0.04%` fee per side and `0.05%` slippage |

Output artifacts:

- Summary: `reports/backtests/20260421T200829Z/summary.md`
- Metrics: `reports/backtests/20260421T200829Z/metrics.json`
- Trades: `reports/backtests/20260421T200829Z/trades.csv`
- Equity curve: `reports/backtests/20260421T200829Z/equity_curve.csv`
- Trained profile: `reports/backtests/20260421T200829Z/trained_profile.json`
- Data audit: `reports/backtests/20260421T200829Z/data_audit.json`

## 3. Data Coverage and Integrity

The original local `history/BTCUSD` files covered December 2025 through March 2026. The loader filled the missing 2025 and warm-up ranges from Binance futures klines. No remaining gaps, duplicate removals, or fetch errors were reported.

| Timeframe | Local Rows Loaded | Rows Fetched | Final Rows | First Timestamp | Last Timestamp | Gaps |
|---|---:|---:|---:|---|---|---:|
| `15m` | `11,296` | `32,384` | `43,680` | `2025-01-01T00:00:00+00:00` | `2026-03-31T23:45:00+00:00` | `0` |
| `4h` | `706` | `3,124` | `3,830` | `2024-07-01T16:00:00+00:00` | `2026-03-31T20:00:00+00:00` | `0` |
| `1d` | `118` | `337` | `455` | `2025-01-01T00:00:00+00:00` | `2026-03-31T00:00:00+00:00` | `0` |

The `4h` series begins before the requested account start because the statistical engine needs warm-up history for HMM and related rolling calculations. The trading account evaluation still begins on `2025-01-01`.

## 4. Aggregate Performance

### Gross Results

Gross results preserve the current paper execution assumptions and do not apply fees or slippage.

| Phase | Trades | Win Rate | Gross PnL | Final Balance | Return | Max Drawdown | Profit Factor | Sharpe | Sortino |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline current settings | `1` | `0.00%` | `-$42,520.00` | `-$37,520.00` | `-850.40%` | `1,844.00%` | `0.00` | `-0.754030` | `-0.037891` |
| Training selected profile | `2` | `50.00%` | `-$162,427.59` | `-$157,427.59` | `-3,248.55%` | `152.74%` | `0.072452` | `1.479533` | `0.750070` |
| Out-of-sample test | `2` | `50.00%` | `-$496,261.77` | `-$491,261.77` | `-9,925.24%` | `780.18%` | `0.098602` | `1.604986` | `0.426768` |

### Net Results

Net results apply `0.04%` fee per side and `0.05%` slippage.

| Phase | Trades | Win Rate | Net PnL | Final Balance | Return | Max Drawdown | Profit Factor | Sharpe | Sortino |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline current settings | `1` | `0.00%` | `-$60,219.95` | `-$55,219.95` | `-1,204.40%` | `1,204.40%` | `0.00` | `-0.895819` | `0.000000` |
| Training selected profile | `2` | `50.00%` | `-$182,428.38` | `-$177,428.38` | `-3,648.57%` | `1,435.10%` | `0.043465` | `-0.879993` | `0.000000` |
| Out-of-sample test | `2` | `50.00%` | `-$549,485.58` | `-$544,485.58` | `-10,989.71%` | `1,087.90%` | `0.083581` | `-0.115891` | `0.000000` |

The results are dominated by very few trades. Win rate and Sharpe are not reliable here because the sample size is too small and balances cross below zero. Once the account becomes insolvent, continued mark-to-market metrics no longer represent a tradable futures account.

## 5. Baseline Current-System Assessment

The baseline profile used the current defaults:

| Parameter | Value |
|---|---:|
| Minimum conviction | `70` |
| Minimum EV | `0.005` |
| Stop loss | `2%` |
| Take profit | `4%` |
| Max risk per trade | `2%` |
| Max daily loss | `5%` |
| Max weekly loss | `10%` |
| Max open positions | `1` |
| Max position duration | `24h` |
| Max leverage | `5x` |
| HMM training window | `1000` |

The baseline opened only one trade:

| Entry Time | Action | Entry | Exit Time | Exit | Size | Exit Reason | Gross PnL | Net PnL |
|---|---|---:|---|---:|---:|---|---:|---:|
| `2025-01-03T20:00:00+00:00` | `LONG` | `$98,545.60` | `2025-01-04T20:00:00+00:00` | `$98,120.40` | `100.00000000` | `MAX_DURATION` | `-$42,520.00` | `-$60,219.95` |

The trade lost only `0.4315%` on price, but the position size was `100 BTC`. At an entry price near `$98,546`, that is roughly `$9.85 million` notional exposure against a `$5,000` account. This is the main failure mode. The strategy did not need a large adverse price move to create catastrophic account loss.

## 6. Training and Parameter Search Result

The training process evaluated bounded parameter candidates across signal thresholds, stop/take-profit settings, risk constants, max duration, leverage, HMM window, and HMM state-label calibration. The selection criteria required:

- At least `10` closed training trades.
- Training max drawdown below `25%`.
- Primary objective: risk-adjusted return.
- Tie-breakers: profit factor, then total PnL.

No candidate met the minimum trade-count and drawdown constraints. The selected profile is therefore a fallback, not a successful trained strategy.

Selected fallback profile:

| Parameter | Selected Value |
|---|---:|
| Minimum conviction | `75` |
| Minimum EV | `0.0025` |
| Stop loss | `2%` |
| Take profit | `4%` |
| Max risk per trade | `0.5%` |
| Max daily loss | `3%` |
| Max weekly loss | `6%` |
| Max open positions | `1` |
| Max position duration | `48h` |
| Max leverage | `2x` |
| HMM training window | `1000` |
| Monte Carlo paths | `10000` |
| Refit interval | `42` candles |

Selected HMM state labels:

```json
["BULL_TREND", "LOW_VOL_RANGE", "BEAR_TREND", "HIGH_VOL_RANGE"]
```

Candidate summary:

| Candidate | Trades | Win Rate | Gross PnL | Gross Return | Max Drawdown | Profit Factor | Accepted |
|---|---:|---:|---:|---:|---:|---:|---|
| `candidate_000` baseline | `1` | `0.00%` | `-$42,520.00` | `-850.40%` | `1,844.00%` | `0.00` | No |
| `candidate_001` selected fallback | `2` | `50.00%` | `-$162,427.59` | `-3,248.55%` | `152.74%` | `0.072452` | No |
| `candidate_002` | `1` | `0.00%` | `-$250,090.00` | `-5,001.80%` | `178.18%` | `0.00` | No |
| `candidate_003` | `1` | `0.00%` | `-$7,535.00` | `-150.70%` | `199.95%` | `0.00` | No |

All candidates failed because they either produced too few trades, exceeded drawdown constraints, or both.

## 7. Training Trades

| Entry Time | Action | Entry | Exit Time | Exit | Size | Exit Reason | Gross PnL | Net PnL |
|---|---|---:|---|---:|---:|---|---:|---:|
| `2025-01-03T16:00:00+00:00` | `LONG` | `$97,479.60` | `2025-01-05T16:00:00+00:00` | `$97,987.10` | `25.00000000` | `MAX_DURATION` | `$12,687.50` | `$8,289.50` |
| `2025-01-06T04:00:00+00:00` | `LONG` | `$99,005.00` | `2025-01-07T17:30:00+00:00` | `$97,024.90` | `88.43750000` | `STOP_LOSS` | `-$175,115.09` | `-$190,717.88` |

The first training trade was profitable, but its size was still large relative to account equity. The second training trade hit a 2% stop loss with `88.4375 BTC` size, producing a gross loss of `-$175,115.09`. This again confirms that the sizing formula, not signal direction alone, is the dominant failure source.

## 8. Out-of-Sample Test Trades

| Entry Time | Action | Entry | Exit Time | Exit | Size | Exit Reason | Gross PnL | Net PnL |
|---|---|---:|---|---:|---:|---|---:|---:|
| `2026-01-05T00:00:00+00:00` | `LONG` | `$91,580.43` | `2026-01-07T00:00:00+00:00` | `$93,751.84` | `25.00000000` | `MAX_DURATION` | `$54,285.25` | `$50,115.28` |
| `2026-01-07T08:00:00+00:00` | `LONG` | `$92,864.08` | `2026-01-07T15:15:00+00:00` | `$91,006.80` | `296.42625000` | `STOP_LOSS` | `-$550,547.02` | `-$599,600.87` |

The selected profile did produce one profitable out-of-sample trade, but the next trade caused a catastrophic stop-loss event. The stop loss worked mechanically, but the position size made the allowed loss many times larger than the account balance.

## 9. Risk-Control Diagnosis

The current system has safety checks for conviction, EV, change-point halt, max open positions, drawdown thresholds, and position sizing. In this backtest those checks did not prevent insolvency.

Primary failure:

- The execution engine treats calculated `size` as BTC quantity.
- The current sizing cap effectively allows `size <= equity * risk_fraction`.
- With `$5,000` equity and `2%` risk, this permits `100` units. For BTC futures, that is interpreted as `100 BTC`, not `$100` notional.
- At BTC prices near `$100,000`, that creates approximately `$10 million` notional exposure.

Consequences:

- A sub-1% price movement can erase the account many times over.
- Daily and weekly loss breakers are not sufficient because the damaging loss occurs inside a single open trade before the breaker can prevent the position from existing.
- Max drawdown and final balance become economically invalid after the account goes below zero.
- The training phase optimizes over a broken risk surface; it cannot produce a reliable model until sizing and margin behavior are fixed.

Secondary concerns:

- Trade count is too low to support claims about edge, calibration, win rate, or Sharpe.
- The mock agent mostly acts on BULL/BEAR trend classifications and does not represent real LLM reasoning.
- No liquidation, maintenance margin, funding, exchange minimums, or bankruptcy price modeling is included.
- The report includes net fee/slippage adjustments, but those are still applied on top of unrealistic notional sizing.

## 10. Interpretation

The backtest answers the original question directly: if the current system had traded with a `$5,000` account over this historical range under the current paper execution semantics, it would have failed catastrophically.

This should not be interpreted as proof that every statistical signal is useless. The result is more specific: the current end-to-end pipeline is not risk-safe because position sizing allows exposure that is inconsistent with account equity. Until that is fixed, model training and parameter tuning are not meaningful.

The trained profile lowered some risk settings from the baseline, including max risk per trade from `2%` to `0.5%` and max leverage from `5x` to `2x`, but the account still failed because the unit semantics remained wrong. Lowering risk constants alone is not enough when `size` is interpreted as BTC quantity.

## 11. Recommended Next Steps

1. Fix position sizing semantics before further model work.
   - Decide whether `size` means BTC quantity, contract quantity, or dollar notional.
   - Make Python and Rust execution engines use the same unit convention.
   - Ensure a 2% stop on a `$5,000` account risks approximately `$100`, not tens of thousands of dollars.

2. Add margin and liquidation modeling to backtests.
   - Futures results should account for initial margin, maintenance margin, liquidation price, funding, and exchange constraints.
   - Prevent negative-balance continuation unless explicitly modeling debt.

3. Add pre-trade notional exposure caps.
   - Cap notional as a function of equity and leverage.
   - Reject any position whose worst-case stop-loss loss exceeds the configured risk budget.

4. Rerun baseline after sizing fixes.
   - Do not tune model parameters until the baseline execution math is valid.
   - Require enough trades before reporting win rate or Sharpe as meaningful.

5. Then rerun training.
   - Use the same 80/20 chronological split.
   - Keep the acceptance rules: at least 10 trades and max drawdown below 25%.
   - Treat any candidate that goes below zero equity as failed.

6. Only after a corrected offline backtest passes should the system move to paper trading.
   - Paper validation should run for multiple weeks before live-capital discussion.
   - Live order placement should remain out of scope until explicitly approved.

## 12. Final Assessment

The current system failed the historical `$5,000` account test. Baseline, trained, and out-of-sample phases all produced unacceptable losses and insolvency-level drawdowns. The primary issue is not a marginal tuning problem; it is a risk and position-sizing contract problem in the current paper execution path.

The next engineering priority should be to correct sizing, margin, and liquidation behavior across both Python and Rust execution paths. After that, the backtest and training workflow created for this run can be reused to produce a more meaningful performance assessment.
