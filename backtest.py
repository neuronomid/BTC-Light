from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from backtesting.profiles import BacktestProfile
from backtesting.reporting import make_run_dir, write_report
from backtesting.runner import BacktestRunner
from backtesting.tuning import candidate_profiles, tune_profiles
from data.historical_loader import HistoricalDataLoader, parse_date_bound


def parse_args():
    parser = argparse.ArgumentParser(description="Offline BTC historical backtest and training report")
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="auto")
    parser.add_argument("--equity", type=float, default=5000.0)
    parser.add_argument("--history-dir", default="history/BTCUSD")
    parser.add_argument("--fetch-missing", action="store_true")
    parser.add_argument("--train-split", type=float, default=0.8)
    parser.add_argument("--tune", choices=["all", "signals", "none"], default="all")
    parser.add_argument("--report-dir", default="reports/backtests")
    parser.add_argument("--data-symbol", default="BTCUSDT")
    parser.add_argument("--max-candidates", type=int, default=10)
    parser.add_argument("--monte-carlo-paths", type=int, default=None)
    parser.add_argument("--refit-interval", type=int, default=42)
    return parser.parse_args()


def main():
    args = parse_args()
    start = parse_date_bound(args.start)
    end = None if args.end == "auto" else parse_date_bound(args.end, is_end=True)

    loader = HistoricalDataLoader(args.history_dir, data_symbol=args.data_symbol)
    bundle = loader.load(
        start,
        end,
        fetch_missing=args.fetch_missing,
        warmup_candles=1100,
    )
    effective_end = pd.Timestamp(bundle.effective_end)

    profile = BacktestProfile.baseline(
        monte_carlo_paths=args.monte_carlo_paths,
        refit_interval_candles=args.refit_interval,
    )
    runner = BacktestRunner(bundle.frames, initial_equity=args.equity)

    baseline = runner.run(
        profile=profile,
        start=start,
        end=effective_end,
        name="baseline_current_settings",
    )
    train_start, train_end, test_end = runner.split_ranges(start, effective_end, args.train_split)
    training_frame = bundle.frames["4h"][
        (bundle.frames["4h"]["timestamp"] < train_end)
    ].copy()
    profiles = candidate_profiles(
        profile,
        tune=args.tune,
        max_candidates=args.max_candidates,
        training_frame=training_frame,
    )

    def run_train(candidate: BacktestProfile):
        return runner.run(profile=candidate, start=train_start, end=train_end, name=f"train_{candidate.name}")

    tuning = tune_profiles(profiles, run_train)
    train_result = tuning.best_train_result
    test_result = runner.run(
        profile=tuning.best_profile,
        start=train_end,
        end=test_end,
        name="test_out_of_sample",
    )

    run_dir = make_run_dir(args.report_dir)
    data_audit = {
        "requested_start": bundle.requested_start,
        "requested_end": bundle.requested_end,
        "effective_start": bundle.effective_start,
        "effective_end": bundle.effective_end,
        "timeframes": bundle.audit,
        "caveats": bundle.caveats,
    }
    paths = write_report(
        run_dir=run_dir,
        baseline=baseline,
        train=train_result,
        test=test_result,
        tuning=tuning,
        data_audit=data_audit,
        caveats=bundle.caveats,
    )

    print(json.dumps({"run_dir": str(run_dir), "outputs": paths, "summary": baseline.metrics}, indent=2))


if __name__ == "__main__":
    main()
