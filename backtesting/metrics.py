from __future__ import annotations

import math
from typing import Dict, Iterable, List

import numpy as np
import pandas as pd


def _profit_factor(values: List[float]) -> float | None:
    gross_profit = sum(v for v in values if v > 0)
    gross_loss = abs(sum(v for v in values if v < 0))
    if gross_loss == 0:
        return None if gross_profit == 0 else math.inf
    return gross_profit / gross_loss


def _max_drawdown(equity: List[float]) -> tuple[float, float]:
    if not equity:
        return 0.0, 0.0
    peak = equity[0]
    max_abs = 0.0
    max_pct = 0.0
    for value in equity:
        peak = max(peak, value)
        drawdown = peak - value
        drawdown_pct = drawdown / peak if peak else 0.0
        max_abs = max(max_abs, drawdown)
        max_pct = max(max_pct, drawdown_pct)
    return max_abs, max_pct


def _sharpe_sortino(equity_curve: List[Dict]) -> tuple[float, float]:
    if len(equity_curve) < 3:
        return 0.0, 0.0
    equity = pd.Series([row["equity"] for row in equity_curve], dtype=float)
    returns = equity.pct_change().dropna()
    if returns.empty:
        return 0.0, 0.0
    periods_per_year = 365 * 6
    std = returns.std(ddof=0)
    sharpe = (returns.mean() / std * math.sqrt(periods_per_year)) if std > 0 else 0.0
    downside = returns[returns < 0]
    downside_std = downside.std(ddof=0)
    sortino = (returns.mean() / downside_std * math.sqrt(periods_per_year)) if downside_std > 0 else 0.0
    return float(sharpe), float(sortino)


def build_net_equity_curve(starting_equity: float, trades: Iterable[Dict], equity_curve: List[Dict]) -> List[Dict]:
    net_balance = starting_equity
    sorted_trades = sorted(trades, key=lambda trade: trade["exit_time"])
    trade_index = 0

    rows = []
    for row in equity_curve:
        row_ts = row["timestamp"]
        while trade_index < len(sorted_trades) and sorted_trades[trade_index]["exit_time"] <= row_ts:
            trade = sorted_trades[trade_index]
            net_balance += trade["net_pnl"]
            trade_index += 1
        rows.append(
            {
                "timestamp": row["timestamp"],
                "balance": round(net_balance, 8),
                "equity": round(net_balance, 8),
                "open_positions": row.get("open_positions", 0),
            }
        )
    while trade_index < len(sorted_trades):
        net_balance += sorted_trades[trade_index]["net_pnl"]
        trade_index += 1
    if rows:
        rows[-1]["balance"] = round(net_balance, 8)
        rows[-1]["equity"] = round(net_balance, 8)
    if not rows:
        rows.append({"timestamp": None, "balance": starting_equity, "equity": starting_equity, "open_positions": 0})
    return rows


def compute_metrics(
    trades: List[Dict],
    equity_curve: List[Dict],
    *,
    starting_equity: float,
    pnl_key: str = "pnl",
) -> Dict:
    values = [float(t[pnl_key]) for t in trades]
    wins = [v for v in values if v > 0]
    losses = [v for v in values if v < 0]
    final_equity = float(equity_curve[-1]["equity"]) if equity_curve else starting_equity
    max_dd_abs, max_dd_pct = _max_drawdown([float(row["equity"]) for row in equity_curve])
    sharpe, sortino = _sharpe_sortino(equity_curve)
    total_pnl = final_equity - starting_equity
    return {
        "starting_balance": round(float(starting_equity), 2),
        "final_balance": round(final_equity, 2),
        "total_pnl": round(float(total_pnl), 2),
        "total_return_pct": round(float(total_pnl / starting_equity), 6) if starting_equity else 0.0,
        "trade_count": len(values),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(len(wins) / len(values), 6) if values else 0.0,
        "avg_win": round(float(np.mean(wins)), 2) if wins else 0.0,
        "avg_loss": round(float(np.mean(losses)), 2) if losses else 0.0,
        "profit_factor": _profit_factor(values),
        "max_drawdown": round(float(max_dd_abs), 2),
        "max_drawdown_pct": round(float(max_dd_pct), 6),
        "sharpe": round(sharpe, 6),
        "sortino": round(sortino, 6),
    }
