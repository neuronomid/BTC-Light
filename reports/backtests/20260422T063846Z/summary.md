# BTC Historical Backtest and Training Report

This is an offline historical paper-trading report. It is not live-capital validation.

## Results

| Phase | Trades | Win Rate | Gross PnL | Gross Balance | Max DD | Profit Factor | Net PnL | Net Balance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline current settings | 128 | 50.00% | $2,958.48 | $7,958.48 | 14.34% | 1.419146022726931 | $1,376.34 | $6,376.34 |
| Training selected profile | 95 | 53.68% | $2,548.21 | $7,548.21 | 10.51% | 1.6616429043156735 | $1,486.18 | $6,486.18 |
| Out-of-sample test | 33 | 39.39% | $374.57 | $5,374.57 | 14.34% | 1.1811008822156026 | $23.23 | $5,023.23 |

## Selected Profile

```json
{
  "name": "trained_selected",
  "min_conviction": 70,
  "min_ev": 0.003,
  "stop_loss_pct": 0.02,
  "take_profit_pct": 0.05,
  "size_multiplier": 1.0,
  "max_risk_per_trade": 0.025,
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

- Trained candidate net PnL (1486.18) did not beat baseline (1486.18) by >5%; reverting to baseline profile.
