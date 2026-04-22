# BTC Futures Backtest Report — Aggressive Sizing Run

Generated: 2026-04-22 UTC
Run directory: `reports/backtests/20260422T073617Z`
Initial account balance: `$5,000.00`
Instrument: BTC perpetual futures proxy data from `history/BTCUSD` plus fetched missing candles
Primary decision timeframe: `4h`
Execution timeframe: `15m`
Fees: `0.04%` per side. Slippage: `0.05%` per side. Round-trip cost modeled: `0.18%` of notional.
Window: `2025-01-01 → 2026-04-01` (15 months), 80/20 train/test split.

This is an offline historical paper-trading assessment. It is not live-capital validation.

## Executive Summary

Starting from the `20% annual strategy` baseline (`report3.md`, ~21.6% annualized), this run pushed position sizing higher to target 40–80% annualized. It produced a **significant lift to ~33.3% annualized** but did not clear the 40% floor. Per the `backtest-strategy` skill the goal was missed, however the user asked for this result to be documented as its own strategy because it is still a large improvement over the prior baseline.

Headline result on the 15-month window with a `$5,000` starting balance:

| Phase | Period | Net Final Balance | Net Return | Annualized | Trades | Max DD | Profit Factor |
|---|---|---:|---:|---:|---:|---:|---:|
| **Baseline (selected)** | 2025-01-01 → 2026-04-01 | **$7,163.74** | **+43.27%** | **~33.3%** | 123 | 25.06% | 1.19 |
| Training (in-sample) | ~2025-01 → 2025-11 | $7,124.75 | +42.49% | ~52.0% | 91 | 25.06% | 1.34 |
| Out-of-sample holdout | 2025-12 → 2026-04 | $5,035.11 | +0.70% | ~2.8% | 32 | 18.99% | 1.01 |

Annualized is computed as `(final/start)^(12/months) - 1`. Baseline window is 15 months; training ~11 months; OOS ~4 months.

The tuner ran 10 candidates. The best scoring candidate did **not** beat baseline net PnL by more than 5%, so the safeguard reverted to baseline — which is what produced the headline result. That means no hyperparameter search was selected; the gains came entirely from the three parameter changes applied to the baseline profile.

## Comparison With Previous Report (20% annual strategy)

| Metric | `report3.md` baseline (20%) | **This run baseline (33%)** | Delta |
|---|---:|---:|---:|
| Net final balance | $6,376.34 | **$7,163.74** | +$787.40 |
| Net return (15 mo) | +27.53% | **+43.27%** | +15.74 pts |
| Annualized | ~21.6% | **~33.3%** | +11.7 pts |
| Trades | 128 | 123 | −5 |
| Net win rate | 48.44% | 47.15% | −1.3 pts |
| Net profit factor | 1.18 | 1.19 | ≈ flat |
| Net max drawdown | 18.42% | **25.06%** | +6.64 pts |
| Net Sharpe | — | 0.87 | — |
| Net Sortino | — | 0.47 | — |

Out-of-sample comparison:

| Metric | `report3.md` OOS (20%) | **This run OOS (33%)** |
|---|---:|---:|
| Net final balance | $5,023.23 | $5,035.11 |
| Net return | +0.46% | +0.70% |
| Trades | 33 | 32 |
| Win rate | 39.39% | 37.50% |
| Profit factor | 1.01 | 1.01 |

## Parameter Changes Made in This Run

Three edits in `backtesting/profiles.py` `BacktestProfile` defaults. No changes to `.env`, `rules_engine/`, `execution_engine/`, or tuner code.

| Parameter | 20% baseline | **33% run** | Rationale |
|---|---:|---:|---|
| `min_ev` | `0.003` | **`0.002`** | Let marginally-positive-EV trades through to attempt raising trade count toward the 150/yr floor. |
| `max_risk_per_trade` | `0.025` | **`0.035`** | Widen the per-trade risk budget so position sizing can scale with Kelly. |
| `kelly_fraction_override` | `0.35` | **`0.55`** | The primary lever — scales the size of every position, directly multiplying PnL (and DD) per trade. |

Everything else remained identical to the 20% strategy: `stop_loss_pct=0.02`, `take_profit_pct=0.05`, `max_position_duration_hours=24`, `min_conviction=70`, `max_leverage=5.0`, `min_time_between_trades_hours=4`, `refit_interval_candles=42`, `hmm_training_window=1000`, `seed=42`.

## Candidate Comparison Table

All 10 tuner candidates used `kelly_fraction_override=0.55` (inherited from the new baseline). `candidate_000` is identical to the new baseline. Scoring rule: `-inf` if trade_count < 20 or net max_dd > 25% else `total_return - 0.5 * max_dd`.

| Candidate | min_ev | SL | TP | risk | lev | conv | HMM win | Net PnL | Trades | WR | PF | Net DD | Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 0.002 | 0.020 | 0.050 | 0.035 | 5.0 | 70 | 1000 | **+$2,124.75** | 91 | 50.5% | 1.34 | 25.06% | -inf |
| 001 | 0.005 | 0.020 | 0.060 | 0.035 | 5.0 | 80 | 750 | +$500.89 | 83 | 41.0% | 1.08 | 17.95% | 0.010 |
| 002 | 0.002 | 0.010 | 0.050 | 0.010 | 3.0 | 70 | 1000 | −$1,413.00 | 243 | 35.4% | 0.85 | 37.12% | -inf |
| 003 | 0.005 | 0.015 | 0.050 | 0.015 | 4.0 | 70 | 1000 | −$553.20 | 164 | 41.5% | 0.93 | 21.99% | -0.221 |
| 004 | 0.0075 | 0.020 | 0.050 | 0.0075 | 2.5 | 70 | 1000 | −$264.81 | 121 | 46.3% | 0.88 | 8.58% | -0.096 |
| 005 | 0.002 | 0.015 | 0.060 | 0.0075 | 2.5 | 75 | 500 | −$460.67 | 123 | 42.3% | 0.80 | 11.46% | -0.149 |
| 006 | 0.002 | 0.015 | 0.060 | 0.010 | 3.0 | 70 | 500 | −$619.93 | 123 | 42.3% | 0.80 | 15.36% | -0.201 |
| 007 | 0.005 | 0.015 | 0.050 | 0.015 | 4.0 | 75 | 1000 | −$553.20 | 164 | 41.5% | 0.93 | 21.99% | -0.221 |
| 008 | 0.005 | 0.020 | 0.050 | 0.015 | 4.0 | 80 | 750 | +$325.11 | 108 | 45.4% | 1.09 | 11.83% | 0.006 |
| 009 | 0.0075 | 0.015 | 0.060 | 0.0075 | 2.5 | 70 | 1000 | −$447.54 | 107 | 39.3% | 0.83 | 12.24% | -0.151 |

Key observation: only 2 of 10 candidates finished net-positive. The tuner cannot find a better-risk-adjusted candidate than the untuned baseline at this Kelly level, because candidates that lower `max_risk_per_trade` / `max_leverage` collapse the per-trade PnL below break-even on fees, while candidates that loosen `min_ev` too far generate trades whose edge doesn't survive costs. Baseline wins by default.

Best non-baseline candidate: `001` (+$500.89) at min_conviction 80, min_ev 0.005 — much more selective but ~half the PnL.

## Root Causes / Hypotheses

1. **Kelly is the dominant lever.** Raising `kelly_fraction_override` from 0.35 → 0.55 scales every position's notional. Gross PnL roughly tracks the ratio: 0.55/0.35 ≈ 1.57x. Observed gross PnL ratio vs. 20% baseline: $4,499 / ~$2,850 ≈ 1.58x. This is almost exactly the expected scaling.
2. **`max_risk_per_trade` 0.025 → 0.035 gave Kelly room to run.** With a 2% SL, Kelly 0.55 on some signals wants to size past the 2.5% per-trade cap — the wider cap unbinds those trades and lets position sizes fully reflect the Kelly recommendation.
3. **`min_ev` 0.002 did not add trades** (128 → 123). The trade-generation bottleneck is upstream of EV filtering. Candidate 002 dropping `min_ev` further while also tightening SL to 0.010 generated 243 trades but net was −28% because the trade-selection quality collapsed.
4. **Drawdown scaled almost linearly with sizing.** Net max DD went from 18.42% → 25.06% (≈1.36x). This is consistent with Kelly-style variance scaling. DD is now sitting on the tuner's 25% kill threshold — there is very little headroom.
5. **Edge did not improve.** Profit factor is flat (1.18 → 1.19) and win rate is flat (48.4% → 47.2%). Only the size-per-trade changed. This is the core limitation: the strategy's structural edge is unchanged — we are compensating for a modest edge with larger bets.

## What We Tried and Discarded

- **Prior attempt in this session (run `20260422T071741Z`)**: ran with the same three parameter changes but **on a truncated 4-month window** because local history was missing 2025-01 through 2025-11. Produced 0 baseline trades, 3 training trades, −$133 OOS. Discarded as invalid — not comparable. This incident prompted the new skill rule requiring verification that the full 15-month window is covered before any run is reported. See `.claude/skills/backtest-strategy/SKILL.md`.

## Limitations

- **Max DD at 25.06%** is at the tuner's rejection ceiling. A real regime stress event could easily push this higher.
- **Out-of-sample is a near-no-op** (+0.70% on 32 trades, WR 37.5%, PF 1.01). The 33% annualized result is concentrated in the ~11-month training window where the walk-forward training's safeguard reverted to baseline. The OOS phase does not independently validate the strategy.
- **Trade count 123 / 15 months = ~98/yr**, well below the project's 150/yr floor. Sample size is still thin.
- Not validated on pre-2025 data. No funding-rate cost modeled.
- No improvement in profit factor or win rate vs the 20% strategy — the gains are purely from sizing. A market with different volatility characteristics could erode the Kelly edge quickly.
- The 40-80% annualized goal was not met; 33% is the ceiling reachable by this set of sizing changes alone.

## Artifact References

- Run directory: `reports/backtests/20260422T073617Z/`
  - `summary.md` — runner summary
  - `metrics.json` — gross/net metrics for baseline + training + test + all candidates
  - `trades.csv` — full trade list
  - `equity_curve.csv` — equity curve
  - `trained_profile.json` — selected profile (reverted to baseline)
  - `data_audit.json` — data window audit
- Strategy snapshot (this run): `strategy/33% annual strategy.md`
- Previous strategy: `strategy/20% annual strategy.md` (report3.md)
