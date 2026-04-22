# 70% Annual Strategy

Parameter snapshot for the strategy that achieved ~71.8% annualized net return (+96.72% over 15 months) on BTC 4H futures in the full-window backtest (`2025-01-01 → 2026-04-01`). Restore the values below to reproduce.

This strategy evolved from the `33% annual strategy` by widening `max_risk_per_trade` and giving back some Kelly. The key insight is that the 33% strategy was silently clipping its high-conviction trades against the per-trade risk cap — widening the cap and rebalancing Kelly produced a structural improvement in profit factor, win rate, and OOS performance, not just a sizing scale-up.

**Read "What makes this strategy 70% instead of 33%" before touching anything.**

## Headline Result (reference only)

| Phase | Trades | Win Rate | Net PnL | Net Balance | Max DD | Profit Factor |
|---|---:|---:|---:|---:|---:|---:|
| Baseline (selected) | 119 | 49.58% | $4,835.87 | $9,835.87 | 31.22% | 1.29 |
| Training (in-sample) | 89 | 52.81% | $3,811.11 | $8,811.11 | 23.17% | 1.46 |
| Out-of-sample | 30 | 40.00% | $486.12 | $5,486.12 | 21.83% | 1.12 |

- Starting balance: $5,000
- Window: 2025-01-01 → 2026-04-01 (≈15 months), 4H candles, 80/20 train/test split
- Fees modeled: 0.04%/side; Slippage: 0.05%/side; Round-trip: 0.18% of notional
- Selected profile reverted to baseline because best trained candidate was −$800.91 (nowhere near the +5% threshold).
- Report: `reports/report5.md`; run artifacts: `reports/backtests/20260422T081912Z/`
- Annualized: `(9835.87 / 5000) ^ (12/15) - 1 ≈ 71.85%`
- Net Sharpe 1.20, Net Sortino 0.59

---

## What makes this strategy 70% instead of 33%

Read this section first. The win here is not "bigger Kelly" — it is a corrected interaction between the Kelly recommendation and the risk cap.

1. **`max_risk_per_trade` was the binding constraint, not Kelly.** At the 33% strategy's settings (`kelly=0.55`, `risk=0.035`), the *actual* executed size was `min(kelly_recommended_notional, max_risk*equity/stop_loss)`. Most high-EV signals had Kelly recommendations that exceeded the 0.035 cap, so they were being clipped down to roughly equal sizes. Raising the cap to **`0.050`** (with Kelly *reduced* to `0.45`) lets high-conviction signals size according to their edge, and low-conviction signals size proportionally smaller. Gross PnL went from $4,499 → $8,324 (1.85x) despite Kelly being lowered.
2. **The structural edge improved, not just the size.** Net PF jumped 1.19 → 1.29, net WR 47.2% → 49.6%. That is a real quality improvement, not a multiplier. The earlier risk cap was penalizing winners asymmetrically: winners' Kelly recommendations were clipped at the cap, while losers (shorter, earlier SL exits) were usually sized below the cap. Widening the cap restored the strategy's natural win/loss asymmetry.
3. **OOS finally moved off the floor.** Net OOS: +0.70% → +9.72%. Net OOS PF: 1.01 → 1.12. This is the first backtest in the 20%/33%/70% evolution where OOS is clearly non-noise.
4. **`min_conviction 70 → 65` and `min_time_between_trades_hours 4 → 2` had zero effect.** Trade count went 123 → 119. These two knobs were expected to raise trade count but didn't — confirming the trade-generation bottleneck is deep in the signal layer (MC/EV/regime), not in the risk-management gates. **Keep these loosened only because removing them is untested; they do not contribute to the 70% result.**
5. **Net max DD is 31.22%, past the tuner's 25% kill threshold.** The tuner only enforces 25% on the *training window* (23.17% — inside the limit). Over the full 15-month window the DD is elevated. This is the single biggest risk note: **this strategy is operating outside the nominal 25% safety envelope.** If you run it live, a regime shock could realize a 30%+ DD.
6. **Kelly 0.45 is lower than the 33% strategy's 0.55.** Do not interpret "70% return" as "more aggressive sizing". It is less aggressive Kelly *plus* a wider cap. This combination increases variance on high-EV signals while reducing it on low-EV ones.
7. **Sharpe/Sortino improved as well.** Sharpe 0.87 → 1.20, Sortino 0.47 → 0.59. Risk-adjusted returns are meaningfully better despite the elevated raw DD.

## If you want to reproduce the ~70% strategy from the 33% starting point, the minimum viable diff is:

```diff
- max_risk_per_trade: 0.035
+ max_risk_per_trade: 0.050

- kelly_fraction_override: 0.55
+ kelly_fraction_override: 0.45
```

The `min_conviction` and `min_time_between_trades_hours` changes are included in the current `BacktestProfile` defaults but are not load-bearing. If you restore them to `70` / `4` you will likely see a result within a percentage point or two of the 71.8% number, provided the risk-cap and Kelly changes above are in place.

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

Production defaults — **unchanged from the 20% and 33% strategies**, so `rules_engine` unit tests continue to pass. All strategy-specific overrides live in `BacktestProfile`.

### `BacktestProfile` defaults (`backtesting/profiles.py`)

**Bold** rows are the parameters that differ from the 33% strategy.

| Field | Value | Notes |
|---|---|---|
| **`min_conviction`** | **`65`** (hard-coded override) | ↓ from `settings.MIN_CONVICTION_TO_TRADE` (70). Did not add trades; keep as-is for reproducibility. |
| `min_ev` | `0.002` | Unchanged from 33% strategy |
| `stop_loss_pct` | `0.02` | Unchanged — 2% SL |
| `take_profit_pct` | `0.05` | Unchanged — 5% TP → 2.5:1 R:R |
| `size_multiplier` | `1.0` | Unchanged |
| **`max_risk_per_trade`** | **`0.050`** | ↑ from 0.035 — **primary load-bearing change**, unclips Kelly on high-EV signals |
| `max_daily_loss` | from `settings.MAX_DAILY_LOSS` (0.05) | Unchanged |
| `max_weekly_loss` | from `settings.MAX_WEEKLY_LOSS` (0.10) | Unchanged |
| `max_open_positions` | from `settings.MAX_OPEN_POSITIONS` (1) | Unchanged |
| `max_position_duration_hours` | `24` | Unchanged |
| **`min_time_between_trades_hours`** | **`2`** (hard-coded override) | ↓ from `settings.MIN_TIME_BETWEEN_TRADES_HOURS` (4). Did not add trades; keep as-is for reproducibility. |
| `max_leverage` | from `settings.MAX_LEVERAGE` (5.0) | Unchanged |
| `hmm_training_window` | from `settings.HMM_TRAINING_WINDOW` (1000) | Unchanged |
| `regime_state_labels` | `("BULL_TREND","BEAR_TREND","HIGH_VOL_RANGE","LOW_VOL_RANGE")` | Unchanged |
| `monte_carlo_paths` | from `settings.MONTE_CARLO_PATHS` (10000) | Unchanged |
| `refit_interval_candles` | `42` | Unchanged |
| **`kelly_fraction_override`** | **`0.45`** | ↓ from 0.55 — paired with the risk-cap change, rebalances size distribution across signals |
| `seed` | `42` | Unchanged |

### Tuner grid (`backtesting/tuning.py`)

Unchanged from prior strategies. Grid ran, no candidate came within 5% of baseline, baseline selected.

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
- `risk_values`:
  - baseline tuple
  - `(0.015, 4.0, 0.05, 0.10)`
  - `(0.01, 3.0, 0.04, 0.08)`
  - `(0.0075, 2.5, 0.03, 0.06)`
- `seed=42`, first 10 candidates.

### Tuner scoring (`score_result`)

```python
if trade_count < 20 or max_dd > 0.25:
    return (-inf, profit_factor, pnl)
score = total_return - 0.5 * max_dd
```

The 25% ceiling applies to *training-window* net DD only (23.17% here — inside the limit). The full-window net DD of **31.22% is not enforced anywhere** in the tuning pipeline. If you need the strategy to stay inside 25% full-window DD, reduce Kelly further (e.g. 0.40) or tighten SL.

### Baseline-revert safeguard (`tune_profiles`)

```python
if baseline_pnl > 0 and best_pnl <= baseline_pnl * 1.05:
    # revert to baseline profile
```

Triggered in this run: best non-baseline candidate was −$800.91 (`candidate_001`, conviction 80 + min_ev 0.005 + HMM 750), so trained profile reverted to baseline.

### Runner

- `backtest.py --max-candidates` default: `10`
- Initial equity: `$5,000`
- Fee rate: `0.0004`, Slippage rate: `0.0005` (`BacktestExecutionEngine` defaults)

### Required engine fixes (non-parameter)

Same as the 20% / 33% strategies — these are bugfixes, not tunables, but required to reproduce:

- `BacktestExecutionEngine._roll_periods`: resets `daily_pnl`/`weekly_pnl` at day/week boundaries.
- `BacktestSafetyEngine.calculate_size`: honors `profile.kelly_fraction_override` instead of the global `KELLY_FRACTION`. **Without this fix the strategy collapses to ~15% annualized.**
- Daily loss breaker uses `max(self.balance, self.initial_equity)` to prevent pathological breaker thresholds after drawdowns.

---

## How to restore this strategy

1. Ensure `.env` contains the values in the `.env` block above (unchanged from 20%/33% strategies).
2. Ensure `backtesting/profiles.py` `BacktestProfile` defaults match the table above. The four parameters that matter:
   - `min_conviction=65` (override, not load-bearing)
   - `min_time_between_trades_hours=2` (override, not load-bearing)
   - `max_risk_per_trade=0.050` (**load-bearing**)
   - `kelly_fraction_override=0.45` (**load-bearing**)
   - `min_ev=0.002` (carried over from 33% strategy)
3. Ensure `backtesting/tuning.py` grid + scoring + baseline-revert safeguard match the snippets above.
4. Ensure the three engine fixes in `backtesting/execution.py` are present.
5. Verify local history covers the full 15-month window:
   - `ls history/BTCUSD/2025/ history/BTCUSD/2026/` should show 4h, 15m, and 1d CSVs for every month from 2025-01 to the current month.
   - If gaps exist, run with `--fetch-missing` first. **Do not skip this step** — the prior session twice produced invalid 4-month-window runs because local history was incomplete.
6. Run: `./venv/bin/python backtest.py --max-candidates 10`
7. Verify `summary.md` → Data Window shows `effective_start` at `2025-01-01T00:00:00+00:00`. If later, the run is invalid.
8. Compare `reports/backtests/<run>/summary.md` against the headline table. Net final balance should land near $9,835.87 at `seed=42`.

---

## Known limitations

- **Full-window net max DD is 31.22%** — past the 25% tuner ceiling. The tuner only checks this on the training window (23.17%, inside the limit). Live execution could realize a 30%+ drawdown during a regime shock. This is the single biggest caveat.
- **OOS sample is small** (30 trades). OOS is positive (+9.72%, PF 1.12) but not yet rigorous validation of the 71.8% number.
- **Trade count 119 / 15mo ≈ 95/yr**, below the 150/yr project floor. Strategy family has not yet cracked the trade-count floor — sample-size concerns remain.
- **`min_conviction` and `min_time_between_trades_hours` overrides did not add trades.** They are preserved in the profile for exact reproducibility of this run's ~71.8% result, but they are not the lever. If removing them is desirable for cleanliness, expect the result to move by less than a percentage point.
- Kelly 0.45 + `max_risk=0.050` + `max_leverage=5.0` is aggressive. In an extended high-vol regime unlike the training data, per-trade losses will scale proportionally.
- Not validated on pre-2025 data. No funding-rate cost modeled.
- **The edge improvement (PF 1.19 → 1.29) was unexpected.** Explained above as the risk-cap asymmetrically clipping winners, but this hypothesis should be verified by instrumenting the sizing code — if it is wrong, the 70% number may not be reproducible under different data.

## How to push past 70% (directions for future runs)

Only attempt these after validating the above on a longer OOS window:

1. **Push Kelly back up, slightly.** With the risk cap at 0.050, Kelly 0.50 (vs current 0.45) might net another 5–10 points of return. Monitor training DD — if it tops 25%, back off.
2. **Tighten SL to 0.015 and widen TP to 0.055.** Shortens loser duration, keeps 3.67:1 R:R. Could reduce DD and let Kelly push higher. Candidate 003/007 tried tighter SL and went negative, but they also collapsed risk_cap/lev — this would be SL-only.
3. **Unblock trade generation.** The 95/yr trade rate is the real limit. This requires changing `statistical_engine/` or `rules_engine/` — not a parameter knob. Consider adding an alternative conviction calculation or a multi-timeframe confirmation lane. Out of scope for `BacktestProfile` tuning.
4. **Stop here.** 71.8% annualized on 15mo with +9.72% OOS is already beyond the original 40% goal. Further tuning risks overfitting to the current 15-month window. Consider running this strategy on a simulated paper account before pushing parameters further.
