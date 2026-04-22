# BTC Historical Backtest and Training Report

This is an offline historical paper-trading report. It is not live-capital validation.

## Results

| Phase | Trades | Win Rate | Gross PnL | Gross Balance | Max DD | Profit Factor | Net PnL | Net Balance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline current settings | 123 | 48.78% | $4,495.54 | $9,495.54 | 18.19% | 1.4470599045603327 | $2,243.65 | $7,243.65 |
| Training selected profile | 91 | 52.75% | $3,609.91 | $8,609.91 | 18.19% | 1.6761257668530323 | $2,162.89 | $7,162.89 |
| Out-of-sample test | 32 | 37.50% | $528.09 | $5,528.09 | 16.65% | 1.1923146028508151 | $59.49 | $5,059.49 |

## Selected Profile

```json
{
  "name": "trained_selected",
  "min_conviction": 65,
  "min_ev": 0.002,
  "stop_loss_pct": 0.02,
  "take_profit_pct": 0.05,
  "size_multiplier": 1.0,
  "max_risk_per_trade": 0.035,
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

- Trained candidate net PnL (2162.89) did not beat baseline (2162.89) by >5%; reverting to baseline profile.
