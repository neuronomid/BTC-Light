# BTC Historical Backtest and Training Report

This is an offline historical paper-trading report. It is not live-capital validation.

## Results

| Phase | Trades | Win Rate | Gross PnL | Gross Balance | Max DD | Profit Factor | Net PnL | Net Balance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline current settings | 118 | 40.68% | $1,769.05 | $6,769.05 | 18.44% | 1.2392324958901897 | $620.26 | $5,620.26 |
| Training selected profile | 63 | 33.33% | $-222.93 | $4,777.07 | 10.37% | 0.8277007558267145 | $-415.56 | $4,584.44 |
| Out-of-sample test | 19 | 47.37% | $146.43 | $5,146.43 | 2.81% | 1.4371295203810708 | $86.85 | $5,086.85 |

## Selected Profile

```json
{
  "name": "trained_selected",
  "min_conviction": 70,
  "min_ev": 0.003,
  "stop_loss_pct": 0.02,
  "take_profit_pct": 0.06,
  "size_multiplier": 1.0,
  "max_risk_per_trade": 0.0075,
  "max_daily_loss": 0.03,
  "max_weekly_loss": 0.06,
  "max_open_positions": 1,
  "max_position_duration_hours": 48,
  "min_time_between_trades_hours": 4,
  "max_leverage": 2.5,
  "hmm_training_window": 750,
  "regime_state_labels": [
    "HIGH_VOL_RANGE",
    "BULL_TREND",
    "LOW_VOL_RANGE",
    "BEAR_TREND"
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
