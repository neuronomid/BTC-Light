import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backtesting.execution import BacktestExecutionEngine
from backtesting.metrics import compute_metrics
from backtesting.profiles import BacktestProfile
from backtesting.runner import BacktestRunner
from backtesting.tuning import candidate_profiles, tune_profiles
from data.historical_loader import HistoricalDataLoader, contiguous_missing_ranges, normalize_kline_frame


def kline_row(ts, open_=100, high=101, low=99, close=100.5, volume=10):
    open_us = int(pd.Timestamp(ts, tz="UTC").value // 1000)
    close_us = open_us + 1
    return [open_us, open_, high, low, close, volume, close_us, 0, 1, 0, 0, 0]


def frame(rows, freq="4h"):
    timestamps = pd.date_range("2025-01-01", periods=rows, freq=freq, tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + i for i in range(rows)],
            "high": [102.0 + i for i in range(rows)],
            "low": [98.0 + i for i in range(rows)],
            "close": [101.0 + i for i in range(rows)],
            "volume": [10.0] * rows,
        }
    )


def passing_snapshot():
    return {
        "probability": {"expected_value_per_trade": 0.05, "kelly_fraction": 1.0},
        "change_point": {"recommend_halt": False, "regime_stability_score": 1.0},
        "regime": {"current_state": "BULL_TREND"},
    }


def long_decision():
    return {
        "action": "LONG",
        "conviction": 80,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
        "size_multiplier": 1.0,
        "reasoning": "test",
    }


class TestHistoricalLoader(unittest.TestCase):
    def test_normalize_kline_frame_detects_microsecond_timestamps(self):
        df = normalize_kline_frame(pd.DataFrame([kline_row("2025-01-01T00:00:00Z")]))

        self.assertEqual(str(df.iloc[0]["timestamp"]), "2025-01-01 00:00:00+00:00")
        self.assertEqual(df.iloc[0]["open"], 100)

    def test_local_loader_deduplicates_and_reports_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2025"
            path.mkdir()
            pd.DataFrame(
                [
                    kline_row("2025-01-01T00:00:00Z"),
                    kline_row("2025-01-01T00:00:00Z", close=101),
                    kline_row("2025-01-01T08:00:00Z"),
                ]
            ).to_csv(path / "BTCUSD-4h-2025-01.csv", header=False, index=False)

            df, audit = HistoricalDataLoader(tmp).load_local_timeframe("4h")

        self.assertEqual(len(df), 2)
        self.assertEqual(audit.duplicates_removed, 1)
        self.assertEqual(len(audit.gaps), 1)
        self.assertEqual(audit.gaps[0]["expected_next"], "2025-01-01T04:00:00+00:00")

    def test_fetch_missing_merges_mocked_binance_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "2025"
            path.mkdir()
            pd.DataFrame([kline_row("2025-01-01T00:00:00Z")]).to_csv(
                path / "BTCUSD-4h-2025-01.csv", header=False, index=False
            )
            loader = HistoricalDataLoader(tmp)
            fetched = normalize_kline_frame(pd.DataFrame([kline_row("2025-01-01T04:00:00Z")]))

            with patch.object(loader, "fetch_binance_futures", return_value=fetched):
                bundle = loader.load(
                    pd.Timestamp("2025-01-01T00:00:00Z"),
                    pd.Timestamp("2025-01-01T08:00:00Z"),
                    fetch_missing=True,
                    warmup_candles=0,
                    timeframes=("4h",),
                )

        self.assertEqual(len(bundle.frames["4h"]), 2)
        self.assertEqual(bundle.audit["4h"]["fetched_rows"], 1)
        self.assertEqual(bundle.audit["4h"]["missing_ranges"], [])

    def test_contiguous_missing_ranges_groups_missing_candles(self):
        df = frame(2)
        df = df[df["timestamp"] != pd.Timestamp("2025-01-01T04:00:00Z")]

        missing = contiguous_missing_ranges(
            df,
            pd.Timestamp("2025-01-01T00:00:00Z"),
            pd.Timestamp("2025-01-01T08:00:00Z"),
            "4h",
        )

        self.assertEqual(missing, [(pd.Timestamp("2025-01-01T04:00:00Z"), pd.Timestamp("2025-01-01T08:00:00Z"))])


class TestBacktestExecutionAndMetrics(unittest.TestCase):
    def test_execution_closes_take_profit_from_15m_bar(self):
        profile = BacktestProfile.baseline(monte_carlo_paths=8).with_updates(max_risk_per_trade=0.02)
        engine = BacktestExecutionEngine(profile, initial_equity=10_000)
        pos = engine.open_position(
            decision=long_decision(),
            snapshot=passing_snapshot(),
            entry_time=pd.Timestamp("2025-01-01T00:00:00Z"),
            entry_price=100.0,
        )

        engine.update_bar(
            pd.Series(
                {
                    "timestamp": pd.Timestamp("2025-01-01T00:15:00Z"),
                    "open": 100.0,
                    "high": 104.1,
                    "low": 99.0,
                    "close": 104.0,
                }
            )
        )

        self.assertIsNotNone(pos)
        self.assertEqual(engine.closed_trades[0].exit_reason, "TAKE_PROFIT")
        self.assertGreater(engine.closed_trades[0].pnl, 0)

    def test_execution_uses_stop_first_when_stop_and_target_hit_same_bar(self):
        profile = BacktestProfile.baseline(monte_carlo_paths=8)
        engine = BacktestExecutionEngine(profile, initial_equity=10_000)
        engine.open_position(
            decision=long_decision(),
            snapshot=passing_snapshot(),
            entry_time=pd.Timestamp("2025-01-01T00:00:00Z"),
            entry_price=100.0,
        )

        engine.update_bar(
            pd.Series(
                {
                    "timestamp": pd.Timestamp("2025-01-01T00:15:00Z"),
                    "open": 100.0,
                    "high": 105.0,
                    "low": 98.0,
                    "close": 100.0,
                }
            )
        )

        self.assertEqual(engine.closed_trades[0].exit_reason, "STOP_LOSS")
        self.assertLess(engine.closed_trades[0].pnl, 0)

    def test_metrics_report_win_rate_balance_drawdown_and_profit_factor(self):
        trades = [{"pnl": 100.0, "net_pnl": 90.0}, {"pnl": -50.0, "net_pnl": -60.0}]
        equity_curve = [
            {"timestamp": "a", "equity": 1000.0},
            {"timestamp": "b", "equity": 1100.0},
            {"timestamp": "c", "equity": 1050.0},
        ]

        metrics = compute_metrics(trades, equity_curve, starting_equity=1000.0)

        self.assertEqual(metrics["trade_count"], 2)
        self.assertEqual(metrics["win_rate"], 0.5)
        self.assertEqual(metrics["total_pnl"], 50.0)
        self.assertEqual(metrics["final_balance"], 1050.0)
        self.assertEqual(metrics["profit_factor"], 2.0)
        self.assertAlmostEqual(metrics["max_drawdown_pct"], 50 / 1100, places=6)


class TestBacktestSplitAndTuning(unittest.TestCase):
    def test_split_ranges_is_chronological(self):
        frames = {"4h": frame(10), "15m": frame(160, freq="15min")}
        runner = BacktestRunner(frames, initial_equity=5000)

        start, train_end, end = runner.split_ranges(
            pd.Timestamp("2025-01-01T04:00:00Z"),
            pd.Timestamp("2025-01-03T00:00:00Z"),
            0.8,
        )

        self.assertEqual(start, pd.Timestamp("2025-01-01T04:00:00Z"))
        self.assertLess(train_end, end)
        self.assertGreater(train_end, start)

    def test_tune_profiles_selects_best_training_result(self):
        profiles = [
            BacktestProfile(name="weak", monte_carlo_paths=8),
            BacktestProfile(name="strong", monte_carlo_paths=8),
        ]

        class FakeResult:
            def __init__(self, pnl, profit_factor):
                self.gross_metrics = {
                    "trade_count": 12,
                    "max_drawdown_pct": 0.1,
                    "total_return_pct": pnl / 1000,
                    "profit_factor": profit_factor,
                    "total_pnl": pnl,
                }
                self.net_metrics = self.gross_metrics
                self.caveats = []

        def run_profile(profile):
            if profile.name == "strong":
                return FakeResult(200, 2.0)
            return FakeResult(50, 1.1)

        result = tune_profiles(profiles, run_profile)

        self.assertEqual(result.best_profile.name, "trained_selected")
        self.assertEqual(result.best_train_result.gross_metrics["total_pnl"], 200)

    def test_candidate_profiles_do_not_loosen_risk_controls(self):
        base = BacktestProfile(monte_carlo_paths=8)

        profiles = candidate_profiles(
            base,
            tune="all",
            max_candidates=20,
            training_frame=frame(20),
        )

        for profile in profiles:
            self.assertGreaterEqual(profile.min_ev, base.min_ev)
            self.assertGreaterEqual(profile.min_conviction, base.min_conviction)
            self.assertLessEqual(profile.stop_loss_pct, base.stop_loss_pct)
            self.assertLessEqual(profile.max_risk_per_trade, base.max_risk_per_trade)
            self.assertLessEqual(profile.max_daily_loss, base.max_daily_loss)
            self.assertLessEqual(profile.max_weekly_loss, base.max_weekly_loss)
            self.assertLessEqual(profile.max_position_duration_hours, base.max_position_duration_hours)
            self.assertLessEqual(profile.max_leverage, base.max_leverage)

    def test_tune_profiles_scores_net_result(self):
        profiles = [
            BacktestProfile(name="gross_better", monte_carlo_paths=8),
            BacktestProfile(name="net_better", monte_carlo_paths=8),
        ]

        class FakeResult:
            def __init__(self, gross_pnl, net_pnl):
                self.gross_metrics = {
                    "trade_count": 12,
                    "max_drawdown_pct": 0.1,
                    "total_return_pct": gross_pnl / 1000,
                    "profit_factor": 2.0,
                    "total_pnl": gross_pnl,
                }
                self.net_metrics = {
                    "trade_count": 12,
                    "max_drawdown_pct": 0.1,
                    "total_return_pct": net_pnl / 1000,
                    "profit_factor": 1.5,
                    "total_pnl": net_pnl,
                }
                self.caveats = []

        def run_profile(profile):
            if profile.name == "net_better":
                return FakeResult(100, 200)
            return FakeResult(300, 50)

        result = tune_profiles(profiles, run_profile)

        self.assertEqual(result.best_train_result.net_metrics["total_pnl"], 200)


if __name__ == "__main__":
    unittest.main()
