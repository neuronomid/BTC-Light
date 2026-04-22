# BTC Historical Backtest and Training Report

This is an offline historical paper-trading report. It is not live-capital validation.

## Results

| Phase | Trades | Win Rate | Gross PnL | Gross Balance | Max DD | Profit Factor | Net PnL | Net Balance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline current settings | 0 | 0.00% | $0.00 | $5,000.00 | 0.00% | None | $0.00 | $5,000.00 |
| Training selected profile | 3 | 66.67% | $123.60 | $5,123.60 | 0.89% | 4.199985977474639 | $109.75 | $5,109.75 |
| Out-of-sample test | 11 | 36.36% | $-86.31 | $4,913.69 | 3.26% | 0.6314268237089018 | $-133.28 | $4,866.72 |

## Selected Profile

```json
{
  "name": "trained_selected",
  "min_conviction": 75,
  "min_ev": 0.002,
  "stop_loss_pct": 0.015,
  "take_profit_pct": 0.06,
  "size_multiplier": 1.0,
  "max_risk_per_trade": 0.0075,
  "max_daily_loss": 0.03,
  "max_weekly_loss": 0.06,
  "max_open_positions": 1,
  "max_position_duration_hours": 24,
  "min_time_between_trades_hours": 4,
  "max_leverage": 2.5,
  "hmm_training_window": 500,
  "regime_state_labels": [
    "BEAR_TREND",
    "BULL_TREND",
    "LOW_VOL_RANGE",
    "HIGH_VOL_RANGE"
  ],
  "monte_carlo_paths": 10000,
  "refit_interval_candles": 42,
  "kelly_fraction_override": 0.55,
  "seed": 42
}
```

## Data Window

- Requested start: `2025-01-01T00:00:00+00:00`
- Requested end: `2026-04-01T00:00:00+00:00`
- Effective start: `2025-12-04T12:00:00+00:00`
- Effective end: `2026-04-01T00:00:00+00:00`

## Caveats

- HMM needs at least 1000 feature rows.
- Skipped 705 decision candles while statistical warm-up was unavailable.
- HMM needs at least 500 feature rows.
- Skipped 519 decision candles while statistical warm-up was unavailable.
- No candidate met the minimum 20-trade and 25% max-drawdown net training constraints; selected the strongest fallback by tie-breakers.
