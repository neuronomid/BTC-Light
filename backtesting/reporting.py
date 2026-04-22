from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from backtesting.runner import BacktestResult
from backtesting.tuning import TuningResult


def make_run_dir(base_dir: Path | str) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = Path(base_dir) / run_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def write_json(path: Path, payload: Dict):
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")


def write_csv(path: Path, rows: List[Dict]):
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _metric_line(label: str, result: BacktestResult) -> str:
    gross = result.gross_metrics
    net = result.net_metrics
    return (
        f"| {label} | {gross.get('trade_count', 0)} | "
        f"{gross.get('win_rate', 0) * 100:.2f}% | "
        f"${gross.get('total_pnl', 0):,.2f} | ${gross.get('final_balance', 0):,.2f} | "
        f"{gross.get('max_drawdown_pct', 0) * 100:.2f}% | "
        f"{gross.get('profit_factor')} | "
        f"${net.get('total_pnl', 0):,.2f} | ${net.get('final_balance', 0):,.2f} |"
    )


def summary_markdown(
    *,
    baseline: BacktestResult,
    train: BacktestResult,
    test: BacktestResult,
    tuning: TuningResult,
    data_audit: Dict,
    caveats: List[str],
) -> str:
    lines = [
        "# BTC Historical Backtest and Training Report",
        "",
        "This is an offline historical paper-trading report. It is not live-capital validation.",
        "",
        "## Results",
        "",
        "| Phase | Trades | Win Rate | Gross PnL | Gross Balance | Max DD | Profit Factor | Net PnL | Net Balance |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        _metric_line("Baseline current settings", baseline),
        _metric_line("Training selected profile", train),
        _metric_line("Out-of-sample test", test),
        "",
        "## Selected Profile",
        "",
        "```json",
        json.dumps(tuning.best_profile.to_dict(), indent=2),
        "```",
        "",
        "## Data Window",
        "",
        f"- Requested start: `{data_audit.get('requested_start')}`",
        f"- Requested end: `{data_audit.get('requested_end')}`",
        f"- Effective start: `{data_audit.get('effective_start')}`",
        f"- Effective end: `{data_audit.get('effective_end')}`",
        "",
        "## Caveats",
        "",
    ]
    all_caveats = list(dict.fromkeys(caveats + baseline.caveats + train.caveats + test.caveats + tuning.caveats))
    if all_caveats:
        lines.extend([f"- {item}" for item in all_caveats])
    else:
        lines.append("- None recorded.")
    lines.append("")
    return "\n".join(lines)


def write_report(
    *,
    run_dir: Path,
    baseline: BacktestResult,
    train: BacktestResult,
    test: BacktestResult,
    tuning: TuningResult,
    data_audit: Dict,
    caveats: List[str],
) -> Dict[str, str]:
    metrics_payload = {
        "baseline": baseline.metrics,
        "training": train.metrics,
        "test": test.metrics,
        "candidate_summaries": tuning.candidate_summaries,
    }
    all_trades = []
    for phase, result in [("baseline", baseline), ("training", train), ("test", test)]:
        for trade in result.trades:
            row = {"phase": phase}
            row.update(trade)
            all_trades.append(row)
    all_equity = []
    for phase, result in [("baseline", baseline), ("training", train), ("test", test)]:
        for row in result.equity_curve:
            out = {"phase": phase}
            out.update(row)
            all_equity.append(out)

    write_json(run_dir / "metrics.json", metrics_payload)
    write_json(run_dir / "trained_profile.json", tuning.best_profile.to_dict())
    write_json(run_dir / "data_audit.json", data_audit)
    write_csv(run_dir / "trades.csv", all_trades)
    write_csv(run_dir / "equity_curve.csv", all_equity)
    (run_dir / "summary.md").write_text(
        summary_markdown(
            baseline=baseline,
            train=train,
            test=test,
            tuning=tuning,
            data_audit=data_audit,
            caveats=caveats,
        ),
        encoding="utf-8",
    )
    return {
        "summary": str(run_dir / "summary.md"),
        "metrics": str(run_dir / "metrics.json"),
        "trades": str(run_dir / "trades.csv"),
        "equity_curve": str(run_dir / "equity_curve.csv"),
        "trained_profile": str(run_dir / "trained_profile.json"),
        "data_audit": str(run_dir / "data_audit.json"),
    }
