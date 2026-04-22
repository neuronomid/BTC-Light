from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass
from typing import Callable, Dict, List

import pandas as pd

from backtesting.profiles import BacktestProfile
from backtesting.runner import BacktestResult
from backtesting.snapshot import derive_regime_state_labels


@dataclass
class TuningResult:
    best_profile: BacktestProfile
    best_train_result: BacktestResult
    candidate_summaries: List[Dict]
    caveats: List[str]


def candidate_profiles(
    base: BacktestProfile,
    *,
    tune: str,
    max_candidates: int,
    training_frame: pd.DataFrame,
) -> List[BacktestProfile]:
    if tune == "none":
        return [base.with_updates(name="trained_baseline")]

    min_ev_values = [base.min_ev, max(base.min_ev, 0.005), max(base.min_ev, 0.0075)]
    stop_target_pairs = [
        (base.stop_loss_pct, base.take_profit_pct),
        (base.stop_loss_pct, max(base.take_profit_pct, 0.06)),
        (min(base.stop_loss_pct, 0.015), max(base.take_profit_pct, 0.045)),
        (min(base.stop_loss_pct, 0.015), max(base.take_profit_pct, 0.06)),
        (min(base.stop_loss_pct, 0.01), max(base.take_profit_pct, 0.03)),
    ]
    conviction_values = [base.min_conviction, max(base.min_conviction, 75), max(base.min_conviction, 80)]
    duration_values = [
        base.max_position_duration_hours,
        min(base.max_position_duration_hours, 48),
        min(base.max_position_duration_hours, 24),
    ]
    hmm_windows = [base.hmm_training_window, 750, 500]

    if tune == "signals":
        risk_values = [(base.max_risk_per_trade, base.max_leverage, base.max_daily_loss, base.max_weekly_loss)]
    else:
        risk_values = [
            (base.max_risk_per_trade, base.max_leverage, base.max_daily_loss, base.max_weekly_loss),
            (0.015, 4.0, 0.05, 0.10),
            (0.01, 3.0, 0.04, 0.08),
            (0.0075, 2.5, 0.03, 0.06),
        ]

    risk_values = [
        (
            min(max_risk, base.max_risk_per_trade),
            min(leverage, base.max_leverage),
            min(daily_loss, base.max_daily_loss),
            min(weekly_loss, base.max_weekly_loss),
        )
        for max_risk, leverage, daily_loss, weekly_loss in risk_values
    ]

    labels_by_window = {}
    for window in hmm_windows:
        try:
            labels_by_window[window] = derive_regime_state_labels(training_frame, window)
        except Exception:
            labels_by_window[window] = base.regime_state_labels

    grid = []
    for min_ev, sl_tp, conviction, duration, hmm_window, risk in itertools.product(
        min_ev_values,
        stop_target_pairs,
        conviction_values,
        duration_values,
        hmm_windows,
        risk_values,
    ):
        max_risk, leverage, daily_loss, weekly_loss = risk
        grid.append(
            base.with_updates(
                name="candidate",
                min_ev=min_ev,
                stop_loss_pct=sl_tp[0],
                take_profit_pct=sl_tp[1],
                min_conviction=conviction,
                max_position_duration_hours=duration,
                hmm_training_window=hmm_window,
                regime_state_labels=labels_by_window[hmm_window],
                max_risk_per_trade=max_risk,
                max_leverage=leverage,
                max_daily_loss=daily_loss,
                max_weekly_loss=weekly_loss,
            )
        )

    unique = []
    seen = set()
    for profile in [base] + grid:
        key = tuple(sorted(profile.to_dict().items(), key=lambda item: item[0]))
        key = str(key)
        if key not in seen:
            seen.add(key)
            unique.append(profile)

    rng = random.Random(base.seed)
    baseline, rest = unique[0], unique[1:]
    rng.shuffle(rest)
    selected = [baseline] + rest[: max(0, max_candidates - 1)]
    return [
        profile.with_updates(name=f"candidate_{idx:03d}") for idx, profile in enumerate(selected)
    ]


def score_result(result: BacktestResult) -> tuple[float, float, float]:
    metrics = result.net_metrics
    trade_count = metrics.get("trade_count", 0)
    max_dd = metrics.get("max_drawdown_pct", 0.0)
    total_return = metrics.get("total_return_pct", 0.0)
    profit_factor = metrics.get("profit_factor")
    pnl = metrics.get("total_pnl", 0.0)
    if trade_count < 20 or max_dd > 0.25:
        return (-math.inf, profit_factor or 0.0, pnl)
    score = total_return - 0.5 * max_dd
    return (score, profit_factor or 0.0, pnl)


def tune_profiles(
    profiles: List[BacktestProfile],
    run_profile: Callable[[BacktestProfile], BacktestResult],
) -> TuningResult:
    candidate_summaries = []
    evaluated: List[tuple[BacktestProfile, BacktestResult]] = []
    best_profile = profiles[0]
    best_result = run_profile(best_profile)
    evaluated.append((best_profile, best_result))
    best_score = score_result(best_result)

    for index, profile in enumerate(profiles):
        if index == 0:
            result = best_result
        else:
            result = run_profile(profile)
            evaluated.append((profile, result))
        current_score = score_result(result)
        candidate_summaries.append(
            {
                "profile": profile.to_dict(),
                "gross_metrics": result.gross_metrics,
                "net_metrics": result.net_metrics,
                "score": current_score[0],
                "caveats": result.caveats,
            }
        )
        if current_score > best_score:
            best_profile = profile
            best_result = result
            best_score = current_score

    caveats = []
    if best_score[0] == -math.inf:
        caveats.append("No candidate met the minimum 20-trade and 25% max-drawdown net training constraints; selected the strongest fallback by tie-breakers.")
        fallback = max(
            evaluated,
            key=lambda item: (item[1].net_metrics.get("profit_factor") or 0.0, item[1].net_metrics.get("total_pnl", 0.0)),
        )
        best_profile, best_result = fallback

    baseline_profile, baseline_result = evaluated[0]
    baseline_pnl = baseline_result.net_metrics.get("total_pnl", 0.0)
    best_pnl = best_result.net_metrics.get("total_pnl", 0.0)
    if baseline_pnl > 0 and best_pnl <= baseline_pnl * 1.05:
        caveats.append(
            f"Trained candidate net PnL ({best_pnl:.2f}) did not beat baseline ({baseline_pnl:.2f}) by >5%; reverting to baseline profile."
        )
        best_profile, best_result = baseline_profile, baseline_result

    return TuningResult(
        best_profile=best_profile.with_updates(name="trained_selected"),
        best_train_result=best_result,
        candidate_summaries=candidate_summaries,
        caveats=caveats,
    )
