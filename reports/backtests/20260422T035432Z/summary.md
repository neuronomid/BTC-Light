# BTC Historical Backtest and Training Report

This is an offline historical paper-trading report. It is not live-capital validation.

## Results

| Phase | Trades | Win Rate | Gross PnL | Gross Balance | Max DD | Profit Factor | Net PnL | Net Balance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline current settings | 128 | 50.00% | $2,110.94 | $7,110.94 | 13.39% | 1.3942873055012412 | $925.35 | $5,925.35 |
| Training selected profile | 94 | 54.26% | $1,945.65 | $6,945.65 | 8.44% | 1.6654705584052003 | $1,142.99 | $6,142.99 |
| Out-of-sample test | 34 | 38.24% | $198.44 | $5,198.44 | 13.39% | 1.116801618312366 | $-81.57 | $4,918.43 |

## Selected Profile

```json
{
  "name": "trained_selected",
  "min_conviction": 70,
  "min_ev": 0.005,
  "stop_loss_pct": 0.02,
  "take_profit_pct": 0.05,
  "size_multiplier": 1.0,
  "max_risk_per_trade": 0.02,
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
  "seed": 42
}
```

## Data Window

- Requested start: `2025-01-01T00:00:00+00:00`
- Requested end: `2026-04-02T00:00:00+00:00`
- Effective start: `2025-01-01T00:00:00+00:00`
- Effective end: `2026-04-02T00:00:00+00:00`

## Caveats

- None recorded.
