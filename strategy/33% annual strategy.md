# 33% Annual Strategy

Parameter snapshot for the strategy that achieved ~33.3% annualized net return (+43.27% over 15 months) on BTC 4H futures in the full-window backtest (`2025-01-01 → 2026-04-01`). Restore the values below to reproduce this strategy.

This is the aggressive-sizing variant of the `20% annual strategy`. It keeps the same signal layer (regime HMM, EV filter, conviction gate, MC simulation) and the same stop-loss/take-profit levels — the only differences are position-sizing parameters. If you want to understand *why* this works, read the "What makes this strategy 33% instead of 20%" section below before anything else.

## Headline Result (reference only)

| Phase | Trades | Win Rate | Net PnL | Net Balance | Max DD | Profit Factor |
|---|---:|---:|---:|---:|---:|---:|
| Baseline (selected) | 123 | 47.15% | $2,163.74 | $7,163.74 | 25.06% | 1.19 |
| Training (best candidate) | 91 | 50.55% | $2,124.75 | $7,124.75 | 25.06% | 1.34 |
| Out-of-sample | 32 | 37.50% | $35.11 | $5,035.11 | 18.99% | 1.01 |

- Starting balance: $5,000
- Window: 2025-01-01 → 2026-04-01 (≈15 months), 4H candles, 80/20 train/test split
- Fees modeled: 0.04%/side; Slippage modeled: 0.05%/side; Round-trip: 0.18% of notional
- Selected profile reverted to baseline because trained candidate did not beat baseline by >5% net PnL.
- Report: `reports/report4.md`; run artifacts: `reports/backtests/20260422T073617Z/`
- Annualized: `(7163.74 / 5000) ^ (12/15) - 1 ≈ 33.3%`

---

## What makes this strategy 33% instead of 20%

This is the single most important section. Internalize these points before tweaking anything else.

1. **Kelly sizing is the dominant driver.** `kelly_fraction_override` was raised from `0.35` to `0.55`. Every position's notional scales roughly linearly with this number. Observed gross PnL scaled by ~1.58x versus the 20% baseline, almost exactly matching the 0.55/0.35 = 1.57x ratio. If you want a *single knob* to move the strategy between the 20% and 33% regimes, it is this one.
2. **`max_risk_per_trade` must be loosened in step with Kelly.** Raised from `0.025` to `0.035`. Without this change, the Kelly-recommended sizes clip against the per-trade risk cap and the Kelly bump is wasted. Rule of thumb: `max_risk_per_trade` should stay above roughly `stop_loss_pct * kelly_fraction_override * max_leverage / 10` — in this strategy that's `0.02 * 0.55 * 5.0 / 10 = 0.0055`, so 0.035 gives plenty of headroom.
3. **`min_ev` lowered from 0.003 to 0.002 is cosmetic.** It did not increase trade count (128 → 123). The trade-generation bottleneck is upstream (conviction gate, MC filter, time-between-trades). If you remove the `min_ev` change and keep only the Kelly + risk bumps, you will likely still see most of the 33% result. The EV loosening is included here because it's what was actually tested, not because it's load-bearing.
4. **Profit factor and win rate did not change.** 1.18 → 1.19 PF, 48.4% → 47.1% WR. **The strategy's structural edge is identical to the 20% variant.** The 33% number is bought entirely with size. That is why max DD rose from 18.42% to 25.06% (≈1.36x, matching Kelly variance scaling).
5. **Max DD is at the 25% kill ceiling.** The tuner rejects any candidate with net max DD > 25%. This strategy's baseline sits exactly on that line. Pushing Kelly higher will violate the ceiling. If you need more return you must improve trade quality (not size), or accept running outside the safety envelope.
6. **OOS is essentially flat (+0.70% on 32 trades, PF 1.01, WR 37.5%).** The 33% annualized headline is concentrated in the training window. Do not market this as a 33% out-of-sample result — it isn't one.
7. **Trade count 98/yr is still below the 150/yr project floor.** Pushing trades higher requires changing conviction or time-between-trades, not EV. Candidates in the tuner that did raise trade count (e.g. `candidate_002` with 243 trades) were net-negative because trade quality collapsed.

## If you want to reproduce a ~33% strategy from scratch, the minimum viable diff is:

```diff
- kelly_fraction_override: 0.35
+ kelly_fraction_override: 0.55
- max_risk_per_trade: 0.025
+ max_risk_per_trade: 0.035
```

(The `min_ev` change is optional; test showed it didn't move trade count.)

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

These are the production defaults — **left unchanged from the 20% strategy**, so `rules_engine` unit tests continue to pass. All strategy-specific overrides live in `BacktestProfile`.

### `BacktestProfile` defaults (`backtesting/profiles.py`)

This is where the 33% strategy lives. **Bold** rows are the parameters that differ from the 20% strategy.

| Field | Value | Notes |
|---|---|---|
| `min_conviction` | `70` (from `settings.MIN_CONVICTION_TO_TRADE`) | Unchanged |
| **`min_ev`** | **`0.002`** | ↓ from 0.003 — cosmetic, did not affect trade count |
| `stop_loss_pct` | `0.02` | Unchanged — 2% SL |
| `take_profit_pct` | `0.05` | Unchanged — 5% TP → 2.5:1 R:R |
| `size_multiplier` | `1.0` | Unchanged |
| **`max_risk_per_trade`** | **`0.035`** | ↑ from 0.025 — **load-bearing**, required for Kelly to scale |
| `max_daily_loss` | from `settings.MAX_DAILY_LOSS` (0.05) | Unchanged |
| `max_weekly_loss` | from `settings.MAX_WEEKLY_LOSS` (0.10) | Unchanged |
| `max_open_positions` | from `settings.MAX_OPEN_POSITIONS` (1) | Unchanged |
| `max_position_duration_hours` | `24` | Unchanged |
| `min_time_between_trades_hours` | from `settings.MIN_TIME_BETWEEN_TRADES_HOURS` (4) | Unchanged |
| `max_leverage` | from `settings.MAX_LEVERAGE` (5.0) | Unchanged |
| `hmm_training_window` | from `settings.HMM_TRAINING_WINDOW` (1000) | Unchanged |
| `regime_state_labels` | `("BULL_TREND","BEAR_TREND","HIGH_VOL_RANGE","LOW_VOL_RANGE")` | Unchanged |
| `monte_carlo_paths` | from `settings.MONTE_CARLO_PATHS` (10000) | Unchanged |
| `refit_interval_candles` | `42` | Unchanged |
| **`kelly_fraction_override`** | **`0.55`** | ↑ from 0.35 — **primary driver** of the 33% return |
| `seed` | `42` | Unchanged |

### Tuner grid (`backtesting/tuning.py`)

Unchanged from the 20% strategy. The grid ran but no candidate beat baseline by >5%, so baseline was selected (this is by design — see the safeguard below).

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
- Candidates randomized with `seed=42`, selected first `max_candidates` (=10).

### Tuner scoring (`score_result`)

```python
if trade_count < 20 or max_dd > 0.25:
    return (-inf, profit_factor, pnl)
score = total_return - 0.5 * max_dd
```

The 25% DD ceiling matters here: **this strategy's baseline max DD is 25.06%**, which is why no tuner candidate can match it without either reducing size (losing return) or accepting a DD above the ceiling (getting -inf).

### Baseline-revert safeguard (`tune_profiles`)

```python
if baseline_pnl > 0 and best_pnl <= baseline_pnl * 1.05:
    # revert to baseline profile
```

Triggered in this run: best non-baseline candidate was `candidate_001` with +$500.89 net PnL, far below the baseline's +$2,124.75 in the training window.

### Runner

- `backtest.py --max-candidates` default: `10`
- Initial equity: `$5,000`
- Fee rate: `0.0004`, Slippage rate: `0.0005` (`BacktestExecutionEngine` defaults)

### Required engine fixes (non-parameter)

Same as the 20% strategy — these are bugfixes, not tunables, but required to reproduce results:

- `BacktestExecutionEngine._roll_periods`: resets `daily_pnl`/`weekly_pnl` at day/week boundaries (prior version never reset → false circuit-breaker trips).
- `BacktestSafetyEngine.calculate_size`: honors `profile.kelly_fraction_override` instead of always using global `KELLY_FRACTION`. **Especially important for this strategy** — if this fix is missing, Kelly stays at the production 0.25 and the strategy degrades back to ~15% annualized.
- Daily loss breaker uses `max(self.balance, self.initial_equity)` to avoid pathological shrinking thresholds after drawdowns.

---

## How to restore this strategy

1. Ensure `.env` contains the values in the `.env` block above (same as 20% strategy — no changes needed).
2. Ensure `backtesting/profiles.py` `BacktestProfile` defaults match the table above. The three parameters that matter:
   - `min_ev=0.002`
   - `max_risk_per_trade=0.035`
   - `kelly_fraction_override=0.55`
3. Ensure `backtesting/tuning.py` grid + scoring + baseline-revert safeguard match the snippets above (unchanged from 20% strategy).
4. Ensure the three engine fixes in `backtesting/execution.py` are present (unchanged from 20% strategy).
5. Verify local history covers the full 15-month window:
   - `ls history/BTCUSD/2025/ history/BTCUSD/2026/` should show 4h, 15m, and 1d CSVs for every month from 2025-01 to the current month.
   - If gaps exist, run with `--fetch-missing` first.
6. Run: `./venv/bin/python backtest.py --max-candidates 10`
7. Verify `summary.md` → Data Window shows `effective_start` at `2025-01-01T00:00:00+00:00`. If it's later, the run is invalid — do not compare against the headline table.
8. Compare `reports/backtests/<run>/summary.md` against the headline table. Net final balance should land near $7,163.74 at `seed=42`.

---

## Known limitations

- **Max DD is at the 25% tuner kill ceiling.** A real-world regime stress event could push DD past 25% and produce a larger loss than was observed in-sample. This strategy has essentially zero safety margin on variance.
- **Out-of-sample return is ~flat** (+0.70% on 32 trades, PF 1.01). The 33% annualized headline is almost entirely in-sample. Do not describe this as OOS-validated.
- **Trade count 123 in 15 months ≈ 98/yr**, below the project's 150/yr floor. Sample size remains thin.
- **Profit factor and win rate did not improve** over the 20% strategy. All gains are sizing-driven. This strategy has the same structural edge as the 20% one and is more fragile to regime changes.
- **Kelly 0.55 on 5x max leverage is aggressive.** If BTC enters an extended high-volatility regime that was not represented in the training window, per-trade losses will scale proportionally and the 25% DD could be breached quickly.
- **The 40-80% annualized target was not met.** This strategy is the ceiling reachable by sizing changes alone. Pushing further requires improving trade quality (better signals, better regime filters, better exit logic), not bigger positions.
- Not validated on pre-2025 data. No funding-rate cost modeled.

## How to push past 33% (directions for future runs)

If you come back later wanting to hit 40%+, do *not* just raise Kelly further — you will blow the DD ceiling. Try these instead, in rough order of expected impact:

1. **Loosen the trade-generation gates**, not the EV gate. Specifically: `min_conviction` 70 → 65 and/or `min_time_between_trades_hours` 4 → 2. More trades at the current PF of 1.19 will compound faster without adding per-trade DD.
2. **Tighten exits to cut DD**, then push Kelly higher. Try `stop_loss_pct=0.015` + `take_profit_pct=0.045` (keeps 3:1 R:R with faster exits). If DD drops to ~20%, you can raise Kelly to 0.65 while staying under the 25% ceiling.
3. **Accept a smaller-but-validated win**. Go back to Kelly 0.45, keep `max_risk=0.030`, and focus all effort on OOS robustness — a 28% annualized strategy with OOS PF 1.2 is probably more valuable than this 33% one with OOS PF 1.01.
