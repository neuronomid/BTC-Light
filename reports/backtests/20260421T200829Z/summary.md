# BTC Historical Backtest and Training Report

This is an offline historical paper-trading report. It is not live-capital validation.

## Results

| Phase | Trades | Win Rate | Gross PnL | Gross Balance | Max DD | Profit Factor | Net PnL | Net Balance |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline current settings | 1 | 0.00% | $-42,520.00 | $-37,520.00 | 1844.00% | 0.0 | $-60,219.95 | $-55,219.95 |
| Training selected profile | 2 | 50.00% | $-162,427.59 | $-157,427.59 | 152.74% | 0.07245234964219067 | $-182,428.38 | $-177,428.38 |
| Out-of-sample test | 2 | 50.00% | $-496,261.77 | $-491,261.77 | 780.18% | 0.09860238642584075 | $-549,485.58 | $-544,485.58 |

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
    "BULL_TREND",
    "LOW_VOL_RANGE",
    "BEAR_TREND",
    "HIGH_VOL_RANGE"
  ],
  "monte_carlo_paths": 10000,
  "refit_interval_candles": 42,
  "seed": 42
}
```

## Data Window

- Requested start: `2025-01-01T00:00:00+00:00`
- Requested end: `2026-04-01T00:00:00+00:00`
- Effective start: `2025-01-01T00:00:00+00:00`
- Effective end: `2026-04-01T00:00:00+00:00`

## Caveats

- No candidate met the minimum 10-trade and 25% max-drawdown training constraints; selected the strongest fallback by tie-breakers.
