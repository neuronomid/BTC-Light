# 20% Annual Strategy

Parameter snapshot for the strategy that achieved ~21.6% annualized net return on BTC 4H futures in the full-window backtest (2025-01-01 → 2026-04-02). Restore the values below to reproduce this strategy.

## Headline Result (reference only)

| Phase | Trades | Win Rate | Net PnL | Net Balance | Max DD | Profit Factor |
|---|---:|---:|---:|---:|---:|---:|
| Baseline (selected) | 128 | 50.00% | $1,376.34 | $6,376.34 | 14.34% | 1.42 |
| Training (best candidate) | 95 | 53.68% | $1,486.18 | $6,486.18 | 10.51% | 1.66 |
| Out-of-sample | 33 | 39.39% | $23.23 | $5,023.23 | 14.34% | 1.18 |

- Starting balance: $5,000
- Window: 2025-01-01 → 2026-04-02 (≈15 months), 4H candles
- Fees modeled: 0.04%/side; Slippage modeled: 0.05%/side
- Selected profile reverted to baseline because trained candidate did not beat baseline by >5% net PnL.
- Report: `reports/report3.md`; run artifacts: `reports/backtests/20260422T065509Z/`

---

## Parameters

### `.env` (globals used by `config/settings.py`)

```
SYMBOL=BTC-USD
TIMEFRAME=4h
YF_INTERVAL=1h
LOOKBACK_DAYS=730

MAX_RISK_PER_TRADE=0.02
MAX_DAILY_LOSS=0.05
MAX_WEEKLY_LOSS=0.10
MAX_OPEN_POSITIONS=1
MAX_POSITION_DURATION_HOURS=24
MIN_TIME_BETWEEN_TRADES_HOURS=4
MAX_LEVERAGE=5.0
MIN_CONVICTION_TO_TRADE=70
MIN_EV_TO_TRADE=0.005

KELLY_FRACTION=0.25
```

These are the production defaults — left unchanged so `rules_engine` tests continue to pass. All strategy-specific overrides live in `BacktestProfile`.

### `BacktestProfile` defaults (`backtesting/profiles.py`)

Backtest-only overrides. These are what actually drive the selected strategy.

| Field | Value | Notes |
|---|---|---|
| `min_conviction` | `70` (from `settings.MIN_CONVICTION_TO_TRADE`) | |
| `min_ev` | `0.003` | Lower than production 0.005 — lets more trades through in backtest |
| `stop_loss_pct` | `0.02` | 2% SL |
| `take_profit_pct` | `0.05` | 5% TP → 2.5:1 R:R |
| `size_multiplier` | `1.0` | |
| `max_risk_per_trade` | `0.025` | Backtest-only; production is 0.02 |
| `max_daily_loss` | from `settings.MAX_DAILY_LOSS` (0.05) | |
| `max_weekly_loss` | from `settings.MAX_WEEKLY_LOSS` (0.10) | |
| `max_open_positions` | from `settings.MAX_OPEN_POSITIONS` (1) | |
| `max_position_duration_hours` | `24` | Matches MC horizon (18 × 4H = 72h ceiling) |
| `min_time_between_trades_hours` | from `settings.MIN_TIME_BETWEEN_TRADES_HOURS` (4) | |
| `max_leverage` | from `settings.MAX_LEVERAGE` (5.0) | |
| `hmm_training_window` | from `settings.HMM_TRAINING_WINDOW` | |
| `regime_state_labels` | `("BULL_TREND","BEAR_TREND","HIGH_VOL_RANGE","LOW_VOL_RANGE")` | |
| `monte_carlo_paths` | from `settings.MONTE_CARLO_PATHS` | |
| `refit_interval_candles` | `42` | HMM refit cadence |
| `kelly_fraction_override` | `0.35` | Backtest-only; production `KELLY_FRACTION` is 0.25 |
| `seed` | `42` | |

### Tuner grid (`backtesting/tuning.py`)

Used in the walk-forward training phase; selection reverts to baseline if no candidate beats it by >5% net PnL.

- `min_ev_values = [base.min_ev, max(base.min_ev, 0.005), max(base.min_ev, 0.0075)]`
- `stop_target_pairs`:
  - `(base.sl, base.tp)`
  - `(base.sl, max(base.tp, 0.06))`
  - `(min(base.sl, 0.015), max(base.tp, 0.045))`
  - `(min(base.sl, 0.015), max(base.tp, 0.06))`
  - `(min(base.sl, 0.01), max(base.tp, 0.03))`
- `conviction_values = [base, max(base, 75), max(base, 80)]`
- `duration_values = [base, min(base, 48), min(base, 24)]`
- `hmm_windows = [base, 750, 500]`
- `risk_values` (max_risk, leverage, daily_loss, weekly_loss):
  - baseline tuple
  - `(0.015, 4.0, 0.05, 0.10)`
  - `(0.01, 3.0, 0.04, 0.08)`
  - `(0.0075, 2.5, 0.03, 0.06)`
- Candidates randomized with `seed=42`, selected first `max_candidates`.

### Tuner scoring (`score_result`)

```python
if trade_count < 20 or max_dd > 0.25:
    return (-inf, profit_factor, pnl)
score = total_return - 0.5 * max_dd
```

### Baseline-revert safeguard (`tune_profiles`)

```python
if baseline_pnl > 0 and best_pnl <= baseline_pnl * 1.05:
    # revert to baseline profile
```

### Runner

- `backtest.py --max-candidates` default: `10`
- Initial equity: `$5,000`
- Fee rate: `0.0004`, Slippage rate: `0.0005` (`BacktestExecutionEngine` defaults)

### Required engine fixes (non-parameter)

These are bugfixes, not tunables, but required to reproduce results:

- `BacktestExecutionEngine._roll_periods`: resets `daily_pnl`/`weekly_pnl` at day/week boundaries (prior version never reset → false circuit-breaker trips).
- `BacktestSafetyEngine.calculate_size`: honors `profile.kelly_fraction_override` instead of always using global `KELLY_FRACTION`.
- Daily loss breaker uses `max(self.balance, self.initial_equity)` to avoid pathological shrinking thresholds after drawdowns.

---

## How to restore this strategy

1. Ensure `.env` contains the values in the `.env` block above.
2. Ensure `backtesting/profiles.py` `BacktestProfile` defaults match the table above (especially `min_ev=0.003`, `max_risk_per_trade=0.025`, `kelly_fraction_override=0.35`, `max_position_duration_hours=24`).
3. Ensure `backtesting/tuning.py` grid + scoring + baseline-revert safeguard match the snippets above.
4. Ensure the three engine fixes in `backtesting/execution.py` are present.
5. Run: `python backtest.py --max-candidates 10`
6. Compare `reports/backtests/<run>/summary.md` against the headline table.

## Known limitations

- OOS window is small (33 trades, 39.4% win rate) — full-window result is largely driven by the training window.
- Not validated on pre-2025 data; no funding-rate cost modeled.
- Trade count for full window (128) is below the 150/yr project floor; tighter grids or a longer window may be needed to hit it.
