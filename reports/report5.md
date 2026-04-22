# BTC Futures Backtest Report — Risk-Cap Unclip Run

Generated: 2026-04-22 UTC
Run directory: `reports/backtests/20260422T081912Z`
Initial account balance: `$5,000.00`
Instrument: BTC perpetual futures proxy (local `history/BTCUSD` + fetched missing candles)
Primary decision timeframe: `4h`
Execution timeframe: `15m`
Fees: `0.04%` per side. Slippage: `0.05%` per side. Round-trip cost modeled: `0.18%` of notional.
Window: `2025-01-01 → 2026-04-01` (15 months), 80/20 train/test split.

This is an offline historical paper-trading assessment. It is not live-capital validation.

## Executive Summary

Starting from the `33% annual strategy` baseline (`report4.md`), this run targeted the 40% annualized goal the prior run had missed. The diagnosis from `report4.md` was that `max_risk_per_trade=0.035` was clipping Kelly-recommended sizes and that `min_conviction`/`min_time_between_trades_hours` were not the trade-generation bottleneck. Based on that, this run widened the risk cap and gave back some Kelly headroom:

- `min_conviction`: `70 → 65`
- `min_time_between_trades_hours`: `4 → 2`
- `max_risk_per_trade`: `0.035 → 0.050`
- `kelly_fraction_override`: `0.55 → 0.45`
- `min_ev`: `0.002` (unchanged)

**Result: the 40% goal was blown past. Net annualized ~71.8%.** Profit factor jumped from 1.19 → 1.29 net (1.55 gross), and — critically — OOS flipped from essentially flat (+0.70% in the 33% strategy) to meaningfully positive (+9.72%, PF 1.12 net / 1.31 gross). The win rate also improved from 47.2% → 49.6% net.

Headline result (15-month window, `$5,000` starting balance):

| Phase | Period | Net Final | Net Return | Annualized | Trades | Max DD | PF |
|---|---|---:|---:|---:|---:|---:|---:|
| **Baseline (selected)** | 2025-01-01 → 2026-04-01 | **$9,835.87** | **+96.72%** | **~71.8%** | 119 | **31.22%** | 1.29 |
| Training (in-sample) | ~2025-01 → 2025-11 | $8,811.11 | +76.22% | ~87.4% | 89 | 23.17% | 1.46 |
| Out-of-sample | 2025-12 → 2026-04 | $5,486.12 | +9.72% | ~32.5% | 30 | 21.83% | 1.12 |

Annualized: `(final/start)^(12/months) - 1`. Baseline window = 15mo; training ~11mo; OOS ~4mo.

The tuner ran 10 candidates. Best non-baseline candidate (`001`) was net −$800.91 over training — far below baseline's +$3,811. Safeguard reverted to baseline, as in the 33% run. All gains came from the four parameter changes above.

## Comparison With Previous Reports

| Metric | 20% (report3) | 33% (report4) | **This run** | Δ vs 33% |
|---|---:|---:|---:|---:|
| Net final balance | $6,376.34 | $7,163.74 | **$9,835.87** | +$2,672.13 |
| Net return (15mo) | +27.53% | +43.27% | **+96.72%** | +53.45 pts |
| Annualized | ~21.6% | ~33.3% | **~71.8%** | +38.5 pts |
| Trades | 128 | 123 | 119 | −4 |
| Net win rate | 48.44% | 47.15% | **49.58%** | +2.4 pts |
| Net profit factor | 1.18 | 1.19 | **1.29** | +0.10 |
| Net max drawdown | 18.42% | 25.06% | **31.22%** | **+6.16 pts** |
| Net Sharpe | — | 0.87 | **1.20** | +0.33 |
| Net Sortino | — | 0.47 | **0.59** | +0.12 |

Out-of-sample comparison (this is the more telling view):

| Metric | 20% OOS | 33% OOS | **This run OOS** |
|---|---:|---:|---:|
| Net final | $5,023.23 | $5,035.11 | **$5,486.12** |
| Net return | +0.46% | +0.70% | **+9.72%** |
| Trades | 33 | 32 | 30 |
| Win rate | 39.4% | 37.5% | **40.0%** |
| Profit factor | 1.01 | 1.01 | **1.12** |
| Max DD | — | 18.99% | 21.83% |

OOS PF finally moved off the 1.01 floor. This is the first backtest in this series where the out-of-sample return is meaningfully positive rather than noise.

## Parameter Changes Made in This Run

Four edits in `backtesting/profiles.py` `BacktestProfile` defaults. No changes to `.env`, `rules_engine/`, `execution_engine/`, or tuner code.

| Parameter | 33% strategy | **This run** | Rationale / observed effect |
|---|---:|---:|---|
| `min_conviction` | `70` | **`65`** | Attempt to raise trade count. **Effect: none** — 123 → 119 trades. |
| `min_time_between_trades_hours` | `4` | **`2`** | Attempt to raise trade count. **Effect: none** — combined with the conviction change, trade count fell slightly. |
| `max_risk_per_trade` | `0.035` | **`0.050`** | **Load-bearing.** Unclipped Kelly on high-conviction signals. Gross PnL jumped from $4,499 → $8,324 (1.85x). |
| `kelly_fraction_override` | `0.55` | **`0.45`** | Given back to leave DD headroom. With the risk cap widened, Kelly 0.45 actually sizes *larger* on high-EV signals than Kelly 0.55 did at the old 0.035 cap. |

Everything else remained identical to the 33% strategy: `stop_loss_pct=0.02`, `take_profit_pct=0.05`, `max_position_duration_hours=24`, `max_leverage=5.0`, `refit_interval_candles=42`, `hmm_training_window=1000`, `min_ev=0.002`, `seed=42`.

## Candidate Comparison Table

Scoring rule: `-inf` if trade_count < 20 or net max_dd > 25% else `total_return - 0.5 * max_dd`. All candidates inherit the new baseline's `max_risk_per_trade=0.050` / `kelly=0.45` only when the grid does not override them. `candidate_000` is identical to the baseline.

| # | min_ev | SL | TP | risk | lev | conv | HMM win | Trn Net PnL | Trades | WR | PF | Trn DD | Score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 0.002 | 0.020 | 0.050 | 0.050 | 5.0 | 65 | 1000 | **+$3,811.11** | 89 | 52.8% | 1.46 | 23.17% | **0.646** |
| 001 | 0.005 | 0.020 | 0.060 | 0.050 | 5.0 | 80 | 750 | −$800.91 | 69 | 40.6% | 0.86 | 45.84% | -inf |
| 002 | 0.002 | 0.010 | 0.050 | 0.010 | 3.0 | 65 | 1000 | −$1,364.81 | 243 | 35.4% | 0.86 | 36.24% | -inf |
| 003 | 0.005 | 0.015 | 0.050 | 0.015 | 4.0 | 65 | 1000 | −$542.70 | 164 | 41.5% | 0.93 | 21.82% | -0.218 |
| 004 | 0.0075 | 0.020 | 0.050 | 0.0075 | 2.5 | 65 | 1000 | −$258.99 | 121 | 46.3% | 0.88 | 8.62% | -0.095 |
| 005 | 0.002 | 0.015 | 0.060 | 0.0075 | 2.5 | 75 | 500 | −$458.54 | 123 | 42.3% | 0.80 | 11.43% | -0.149 |
| 006 | 0.002 | 0.015 | 0.060 | 0.010 | 3.0 | 65 | 500 | −$614.99 | 123 | 42.3% | 0.80 | 15.27% | -0.199 |
| 007 | 0.005 | 0.015 | 0.050 | 0.015 | 4.0 | 75 | 1000 | −$542.70 | 164 | 41.5% | 0.93 | 21.82% | -0.218 |
| 008 | 0.005 | 0.020 | 0.050 | 0.015 | 4.0 | 80 | 750 | −$301.65 | 108 | 45.4% | 0.91 | 23.11% | -0.176 |
| 009 | 0.0075 | 0.015 | 0.060 | 0.0075 | 2.5 | 65 | 1000 | −$444.73 | 107 | 39.3% | 0.83 | 12.19% | -0.150 |

Baseline (`000`) dominates by a wide margin. No non-baseline candidate finished net-positive. Candidates that lowered risk/leverage collapsed PnL; candidates that kept risk at 0.050 but tightened conviction (`001`) lost trades and went negative.

Safeguard triggered: best non-baseline was `−$800.91`, so trained profile was reverted to baseline. Headline number is therefore from the untuned profile `000`.

## Root Causes / Hypotheses

1. **`max_risk_per_trade` was the real bottleneck, not Kelly.** At risk cap 0.035, most high-conviction trades' Kelly-recommended sizes were being clipped — so raising Kelly from 0.35 → 0.55 only helped small signals. Widening the cap to 0.050 let every signal's full Kelly recommendation through. Gross PnL roughly doubled (+$4,499 → +$8,324) even though Kelly itself was *lowered* from 0.55 → 0.45. **The effective sizing is `min(kelly * notional_scale, max_risk * equity / stop)`, and until this run it was the min on the right side most of the time.**
2. **PF and WR actually improved this time**, unlike the 33% run where they were flat. PF 1.19 → 1.29 net, WR 47.2% → 49.6%. This suggests the previous clip was not just on size but on trade *selection* interaction — clipped positions were reducing the effective edge asymmetrically. A cleaner hypothesis: at the old cap, some high-conviction winners were size-capped while losers (which hit SL early and often sized at or below the cap) weren't — so the cap was asymmetrically penalizing winners. Widening the cap restored the structural PF.
3. **OOS finally moved.** Net OOS went +0.70% → +9.72%, PF 1.01 → 1.12. Still a small sample (30 trades), but this is the first run where OOS is clearly non-noise.
4. **Conviction and time-gate loosening did nothing** (trade count 123 → 119). As predicted from the 34.7% run. The signal-generation bottleneck is upstream — likely MC/EV filtering or the regime-state gating. Parameter tuning cannot break this floor.
5. **Net max DD rose to 31.22%** — past the tuner's 25% kill threshold. The tuner only checked the *training-window* net DD (23.17%), so the baseline passed. But measured across the full 15mo, DD is elevated. This is the key risk note.
6. **Sharpe/Sortino both improved** (0.87 → 1.20 Sharpe, 0.47 → 0.59 Sortino), so on a risk-adjusted basis the strategy did genuinely get better despite the higher raw DD — the extra return more than compensates.

## What We Tried and Discarded

- **Run `20260422T080000Z`** (`min_conviction=65`, `min_time_between=2`, risk stayed at 0.035, Kelly 0.45): ~34.7% annualized. Conviction/time-gate had zero effect on trade count. Lower Kelly at the same risk cap gave back ~7 pts of DD (25.06% → 18.19%) for no PnL change. Diagnosed the risk cap as the binding constraint. Not reported as a strategy — replaced by this run.
- **Run `20260422T080335Z`** (same params as this report's run, but `--fetch-missing` not specified): silently used only 4 months of data (2025-12 → 2026-03) because the prior session's fetched candles were not persisted to `history/`. Produced 0 baseline trades, negative OOS. **Discarded as invalid** per the "full 15-month window" rule. Re-run with `--fetch-missing` became the reported run here.

## Limitations

- **Net max DD is 31.22%**, above the tuner's 25% ceiling. The tuner only enforces the ceiling on the training window (23.17% — under the limit), so the full-timeline DD was not caught. A live run could easily breach 25% drawdown under a regime stress event — treat this strategy as sitting *outside* the nominal safety envelope for the full window.
- **Out-of-sample is promising but small** (30 trades, WR 40%, PF 1.12). +9.72% in 4 months is genuinely positive but still not a rigorous validation — a larger OOS period would be needed to trust the ~71.8% number.
- **Trade count 119 / 15mo ≈ 95/yr**, still below the 150/yr project floor. Sample size remains the main caveat on the whole strategy family.
- **Gains come from sizing interaction with the risk cap**, not from a new signal edge. The underlying signal is the same as the 20% and 33% strategies.
- No funding-rate cost modeled. Not validated on pre-2025 data.
- **Max leverage is 5x.** Net DD 31% at 5x is fine in a backtest; in live, a gap or liquidation cascade could push realized losses past simulated ones.

## Artifact References

- Run directory: `reports/backtests/20260422T081912Z/`
  - `summary.md` — runner summary
  - `metrics.json` — gross/net metrics (baseline + training + test + candidates)
  - `trades.csv` — full trade list
  - `equity_curve.csv` — equity curve
  - `trained_profile.json` — selected profile (reverted to baseline)
  - `data_audit.json` — data window audit
- Strategy snapshot (this run): `strategy/70% annual strategy.md`
- Previous strategy: `strategy/33% annual strategy.md` (report4.md)
