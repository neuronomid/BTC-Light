# BTC Historical Backtest and Training Report

This is an offline historical paper-trading report. It is not live-capital validation.

## Results

| Phase | Trades | Win Rate | Gross PnL | Gross Balance | Max DD | Profit Factor | Net PnL | Net Balance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline current settings | 123 | 48.78% | $4,499.22 | $9,499.22 | 19.95% | 1.4318649856810743 | $2,163.74 | $7,163.74 |
| Training selected profile | 91 | 52.75% | $3,634.59 | $8,634.59 | 19.95% | 1.6480397060821204 | $2,124.75 | $7,124.75 |
| Out-of-sample test | 32 | 37.50% | $514.42 | $5,514.42 | 16.65% | 1.1842480313234232 | $35.11 | $5,035.11 |

## Selected Profile

```json
{
  "name": "trained_selected",
  "min_conviction": 70,
  "min_ev": 0.002,
  "stop_loss_pct": 0.02,
  "take_profit_pct": 0.05,
  "size_multiplier": 1.0,
  "max_risk_per_trade": 0.035,
  "max_daily_loss": 0.05,
  "max_weekly_loss": 0.1,
  "max_open_positions": 1,
  "max_position_duration_hours": 24,
  "min_time_between_trades_hours": 4,
  "max_leverage": 5.0,
  "hmm_training_window": 1000,
  "regime_state_labels": [
    "BULL_TREND",
    "BEAR_TREND",
    "HIGH_VOL_RANGE",
    "LOW_VOL_RANGE"
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
- Effective start: `2025-01-01T00:00:00+00:00`
- Effective end: `2026-04-01T00:00:00+00:00`

## Caveats

- Trained candidate net PnL (500.89) did not beat baseline (2124.75) by >5%; reverting to baseline profile.
