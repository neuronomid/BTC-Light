# BTC Historical Backtest and Training Report

This is an offline historical paper-trading report. It is not live-capital validation.

## Results

| Phase | Trades | Win Rate | Gross PnL | Gross Balance | Max DD | Profit Factor | Net PnL | Net Balance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline current settings | 6 | 16.67% | $-248.01 | $4,751.99 | 6.36% | 0.34723351179867423 | $-300.65 | $4,699.35 |
| Training selected profile | 130 | 46.92% | $514.32 | $5,514.32 | 6.17% | 1.3190958852472603 | $205.73 | $5,205.73 |
| Out-of-sample test | 32 | 46.88% | $35.22 | $5,035.22 | 2.91% | 1.0892216671299042 | $-34.46 | $4,965.54 |

## Selected Profile

```json
{
  "name": "trained_selected",
  "min_conviction": 75,
  "min_ev": 0.0025,
  "stop_loss_pct": 0.02,
  "take_profit_pct": 0.04,
  "size_multiplier": 1.0,
  "max_risk_per_trade": 0.005,
  "max_daily_loss": 0.03,
  "max_weekly_loss": 0.06,
  "max_open_positions": 1,
  "max_position_duration_hours": 48,
  "min_time_between_trades_hours": 4,
  "max_leverage": 2.0,
  "hmm_training_window": 1000,
  "regime_state_labels": [
    "LOW_VOL_RANGE",
    "HIGH_VOL_RANGE",
    "BULL_TREND",
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
