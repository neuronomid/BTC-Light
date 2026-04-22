# BTC Historical Backtest and Training Report

This is an offline historical paper-trading report. It is not live-capital validation.

## Results

| Phase | Trades | Win Rate | Gross PnL | Gross Balance | Max DD | Profit Factor | Net PnL | Net Balance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline current settings | 119 | 52.10% | $8,324.00 | $13,324.00 | 22.44% | 1.549141673239533 | $4,835.87 | $9,835.87 |
| Training selected profile | 89 | 56.18% | $5,968.95 | $10,968.95 | 19.19% | 1.801957248806356 | $3,811.11 | $8,811.11 |
| Out-of-sample test | 30 | 40.00% | $1,094.64 | $6,094.64 | 19.02% | 1.3101766961821877 | $486.12 | $5,486.12 |

## Selected Profile

```json
{
  "name": "trained_selected",
  "min_conviction": 65,
  "min_ev": 0.002,
  "stop_loss_pct": 0.02,
  "take_profit_pct": 0.05,
  "size_multiplier": 1.0,
  "max_risk_per_trade": 0.05,
  "max_daily_loss": 0.05,
  "max_weekly_loss": 0.1,
  "max_open_positions": 1,
  "max_position_duration_hours": 24,
  "min_time_between_trades_hours": 2,
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
  "kelly_fraction_override": 0.45,
  "seed": 42
}
```

## Data Window

- Requested start: `2025-01-01T00:00:00+00:00`
- Requested end: `2026-04-01T00:00:00+00:00`
- Effective start: `2025-01-01T00:00:00+00:00`
- Effective end: `2026-04-01T00:00:00+00:00`

## Caveats

- Trained candidate net PnL (3811.11) did not beat baseline (3811.11) by >5%; reverting to baseline profile.
