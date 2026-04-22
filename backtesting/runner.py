from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from agent_layer.agents import MockAgentLayer
from backtesting.execution import BacktestExecutionEngine
from backtesting.metrics import build_net_equity_curve, compute_metrics
from backtesting.profiles import BacktestProfile
from backtesting.snapshot import HistoricalSnapshotBuilder, InsufficientHistory
from data.historical_loader import TIMEFRAME_DELTAS, ensure_utc_timestamp


@dataclass
class BacktestResult:
    name: str
    profile: Dict
    metrics: Dict
    gross_metrics: Dict
    net_metrics: Dict
    trades: List[Dict]
    equity_curve: List[Dict]
    rejected_decisions: List[Dict[str, str]]
    caveats: List[str] = field(default_factory=list)


class BacktestRunner:
    def __init__(
        self,
        frames: Dict[str, pd.DataFrame],
        *,
        initial_equity: float,
        fee_rate: float = 0.0004,
        slippage_rate: float = 0.0005,
    ):
        self.frames = frames
        self.initial_equity = initial_equity
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self._snapshot_cache: Dict[tuple, Dict] = {}

    def _decision_rows(self, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        four_h = self.frames["4h"].copy()
        four_h["decision_time"] = pd.to_datetime(four_h["timestamp"], utc=True) + TIMEFRAME_DELTAS["4h"]
        mask = (four_h["decision_time"] >= start) & (four_h["decision_time"] < end)
        return four_h.loc[mask].reset_index()

    def split_ranges(self, start: pd.Timestamp, end: pd.Timestamp, train_split: float) -> tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp]:
        rows = self._decision_rows(start, end)
        if rows.empty:
            return start, end, end
        split_index = max(1, min(len(rows) - 1, int(len(rows) * train_split)))
        split_time = pd.Timestamp(rows["decision_time"].iloc[split_index])
        return start, split_time, end

    def _entry_bar(self, timestamp: pd.Timestamp, fifteen_m: pd.DataFrame, pointer: int) -> Optional[pd.Series]:
        while pointer < len(fifteen_m) and pd.Timestamp(fifteen_m.iloc[pointer]["timestamp"]) < timestamp:
            pointer += 1
        if pointer >= len(fifteen_m):
            return None
        return fifteen_m.iloc[pointer]

    def run(
        self,
        *,
        profile: BacktestProfile,
        start: pd.Timestamp,
        end: pd.Timestamp,
        name: Optional[str] = None,
    ) -> BacktestResult:
        start = ensure_utc_timestamp(start)
        end = ensure_utc_timestamp(end)
        four_h = self.frames["4h"].copy().sort_values("timestamp").reset_index(drop=True)
        fifteen_m = self.frames["15m"].copy().sort_values("timestamp").reset_index(drop=True)
        if four_h.empty:
            return BacktestResult(
                name=name or profile.name,
                profile=profile.to_dict(),
                metrics={},
                gross_metrics={},
                net_metrics={},
                trades=[],
                equity_curve=[],
                rejected_decisions=[],
                caveats=["No 4H candles available for backtest."],
            )

        decision_rows = self._decision_rows(start, end)
        execution = BacktestExecutionEngine(
            profile,
            initial_equity=self.initial_equity,
            fee_rate=self.fee_rate,
            slippage_rate=self.slippage_rate,
        )
        agents = MockAgentLayer()
        snapshots = HistoricalSnapshotBuilder(profile)
        caveats: List[str] = []
        equity_curve: List[Dict] = []
        peak_equity = self.initial_equity
        fifteen_pointer = 0

        def process_15m_until(cutoff: pd.Timestamp):
            nonlocal fifteen_pointer
            while fifteen_pointer < len(fifteen_m):
                bar = fifteen_m.iloc[fifteen_pointer]
                bar_ts = pd.Timestamp(bar["timestamp"])
                if bar_ts >= cutoff:
                    break
                execution.update_bar(bar)
                fifteen_pointer += 1

        def record_equity(timestamp: pd.Timestamp, price: float):
            nonlocal peak_equity
            equity = execution.mark_equity(price)
            peak_equity = max(peak_equity, equity)
            equity_curve.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "balance": round(execution.balance, 8),
                    "equity": round(equity, 8),
                    "drawdown_pct": round((peak_equity - equity) / peak_equity, 8) if peak_equity else 0.0,
                    "open_positions": len(execution.positions),
                }
            )

        warmup_skips = 0
        for local_index, row in decision_rows.iterrows():
            original_index = int(row["index"])
            decision_time = pd.Timestamp(row["decision_time"])
            process_15m_until(decision_time)
            record_equity(decision_time, float(row["close"]))

            if len(execution.positions) >= profile.max_open_positions:
                continue

            try:
                cache_key = (
                    profile.hmm_training_window,
                    profile.regime_state_labels,
                    profile.refit_interval_candles,
                    original_index,
                )
                if cache_key in self._snapshot_cache:
                    snapshot = copy.deepcopy(self._snapshot_cache[cache_key])
                    snapshots._last_df = four_h.iloc[: original_index + 1].copy()
                else:
                    snapshot = snapshots.build(four_h, original_index, decision_time)
                    self._snapshot_cache[cache_key] = copy.deepcopy(snapshot)
            except InsufficientHistory as exc:
                warmup_skips += 1
                if warmup_skips == 1:
                    caveats.append(str(exc))
                continue
            except Exception as exc:
                caveats.append(f"Snapshot failed at {decision_time.isoformat()}: {exc}")
                continue

            ctx = agents.market_context(snapshot)
            news = agents.news_sentiment(snapshot)
            decision = agents.trade_decision(snapshot, ctx, news).model_dump()
            if decision.get("action") not in ("LONG", "SHORT"):
                continue
            decision["stop_loss_pct"] = profile.stop_loss_pct
            decision["take_profit_pct"] = profile.take_profit_pct
            decision["size_multiplier"] = profile.size_multiplier

            probability = snapshots.evaluate_trade(
                snapshot,
                decision["action"],
                profile.stop_loss_pct,
                profile.take_profit_pct,
                seed=profile.seed + original_index,
            )
            snapshot["probability"] = probability

            entry = self._entry_bar(decision_time, fifteen_m, fifteen_pointer)
            if entry is None:
                caveats.append(f"No 15m entry bar available at or after {decision_time.isoformat()}.")
                continue
            execution.open_position(
                decision=decision,
                snapshot=snapshot,
                entry_time=pd.Timestamp(entry["timestamp"]),
                entry_price=float(entry["open"]),
            )

        process_15m_until(end)
        final_price = None
        final_timestamp = end
        if not fifteen_m.empty:
            eligible = fifteen_m[fifteen_m["timestamp"] < end]
            if not eligible.empty:
                final_row = eligible.iloc[-1]
                final_price = float(final_row["close"])
                final_timestamp = pd.Timestamp(final_row["timestamp"])
        if final_price is None:
            final_price = float(four_h[four_h["timestamp"] < end]["close"].iloc[-1])
        execution.force_close_all(timestamp=final_timestamp, price=final_price)
        record_equity(final_timestamp, final_price)

        trades = [trade.to_dict() for trade in execution.closed_trades]
        gross_metrics = compute_metrics(trades, equity_curve, starting_equity=self.initial_equity, pnl_key="pnl")
        net_curve = build_net_equity_curve(self.initial_equity, trades, equity_curve)
        net_metrics = compute_metrics(trades, net_curve, starting_equity=self.initial_equity, pnl_key="net_pnl")
        metrics = {"gross": gross_metrics, "net": net_metrics}
        if warmup_skips:
            caveats.append(f"Skipped {warmup_skips} decision candles while statistical warm-up was unavailable.")

        return BacktestResult(
            name=name or profile.name,
            profile=profile.to_dict(),
            metrics=metrics,
            gross_metrics=gross_metrics,
            net_metrics=net_metrics,
            trades=trades,
            equity_curve=equity_curve,
            rejected_decisions=execution.rejected_decisions,
            caveats=caveats,
        )
