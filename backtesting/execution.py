from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

import pandas as pd

from config.settings import KELLY_FRACTION


@dataclass
class BacktestPosition:
    trade_id: str
    action: str
    entry_time: pd.Timestamp
    entry_price: float
    size: float
    stop_loss: float
    take_profit: float
    conviction: int
    reasoning: str
    regime: str


@dataclass
class BacktestTrade:
    trade_id: str
    action: str
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    size: float
    stop_loss: float
    take_profit: float
    pnl: float
    pnl_pct: float
    net_pnl: float
    net_pnl_pct: float
    exit_reason: str
    conviction: int
    regime: str
    reasoning: str

    def to_dict(self) -> Dict:
        return asdict(self)


class BacktestSafetyEngine:
    def __init__(self, profile):
        self.profile = profile

    def check_all(
        self,
        decision: Dict,
        stats: Dict,
        *,
        equity: float,
        open_positions: int,
        daily_pnl: float,
        weekly_pnl: float,
        last_trade_time: Optional[pd.Timestamp],
        now: pd.Timestamp,
    ) -> tuple[bool, str]:
        if decision.get("action") == "NO_TRADE":
            return True, "No trade requested."
        if decision.get("conviction", 0) < self.profile.min_conviction:
            return False, f"Conviction {decision.get('conviction')} < {self.profile.min_conviction}"
        prob = stats.get("probability", {})
        if prob.get("expected_value_per_trade", 0) < self.profile.min_ev:
            return False, f"EV {prob.get('expected_value_per_trade')} < {self.profile.min_ev}"
        cp = stats.get("change_point", {})
        if cp.get("recommend_halt", False):
            return False, "Change point detection recommends halt."
        if open_positions >= self.profile.max_open_positions:
            return False, f"Max open positions {self.profile.max_open_positions} reached."
        if daily_pnl < -self.profile.max_daily_loss * equity:
            return False, f"Daily loss circuit breaker triggered: {daily_pnl}"
        if weekly_pnl < -self.profile.max_weekly_loss * equity:
            return False, f"Weekly loss circuit breaker triggered: {weekly_pnl}"
        if last_trade_time is not None:
            elapsed = now - last_trade_time
            min_gap = pd.Timedelta(hours=self.profile.min_time_between_trades_hours)
            if elapsed < min_gap:
                return False, f"Minimum time between trades not met: {elapsed}"
        return True, "All safety checks passed."

    def calculate_size(
        self,
        decision: Dict,
        stats: Dict,
        *,
        equity: float,
        entry_price: float,
        stop_loss_price: float,
    ) -> float:
        if equity <= 0 or entry_price <= 0 or stop_loss_price <= 0 or entry_price == stop_loss_price:
            return 0.0
        kelly = max(stats.get("probability", {}).get("kelly_fraction", 0) or 0.0, 0.0)
        stability = stats.get("change_point", {}).get("regime_stability_score", 1.0) or 1.0
        stability = max(0.0, min(stability, 1.0))
        multiplier = max(0.0, min(decision.get("size_multiplier", 1.0) or 1.0, 1.0))
        kelly_frac = getattr(self.profile, "kelly_fraction_override", None) or KELLY_FRACTION
        risk_fraction = min(kelly * kelly_frac, self.profile.max_risk_per_trade) * stability * multiplier
        if risk_fraction <= 0:
            return 0.0
        risk_budget_usd = equity * risk_fraction
        sl_dist_usd = abs(entry_price - stop_loss_price)
        size_units = risk_budget_usd / sl_dist_usd
        max_notional_usd = equity * max(self.profile.max_leverage, 0.0)
        max_size_units = max_notional_usd / entry_price
        size_units = min(size_units, max_size_units)
        return round(max(size_units, 0.0), 8)


class BacktestExecutionEngine:
    def __init__(
        self,
        profile,
        *,
        initial_equity: float,
        fee_rate: float = 0.0004,
        slippage_rate: float = 0.0005,
    ):
        self.profile = profile
        self.initial_equity = initial_equity
        self.balance = initial_equity
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self._current_day: Optional[pd.Timestamp] = None
        self._current_week: Optional[pd.Timestamp] = None
        self.positions: List[BacktestPosition] = []
        self.closed_trades: List[BacktestTrade] = []
        self.last_trade_time: Optional[pd.Timestamp] = None
        self.safety = BacktestSafetyEngine(profile)
        self.fee_rate = fee_rate
        self.slippage_rate = slippage_rate
        self.rejected_decisions: List[Dict[str, str]] = []

    def _roll_periods(self, ts: pd.Timestamp) -> None:
        day = pd.Timestamp(ts).normalize()
        week = day - pd.Timedelta(days=day.weekday())
        if self._current_day is None or day != self._current_day:
            self._current_day = day
            self.daily_pnl = 0.0
        if self._current_week is None or week != self._current_week:
            self._current_week = week
            self.weekly_pnl = 0.0

    def open_position(
        self,
        *,
        decision: Dict,
        snapshot: Dict,
        entry_time: pd.Timestamp,
        entry_price: float,
    ) -> Optional[BacktestPosition]:
        if self.balance <= 0:
            self.rejected_decisions.append({"timestamp": entry_time.isoformat(), "reason": "Account insolvent (balance <= 0)."})
            return None
        self._roll_periods(entry_time)
        passed, reason = self.safety.check_all(
            decision,
            snapshot,
            equity=self.balance,
            open_positions=len(self.positions),
            daily_pnl=self.daily_pnl,
            weekly_pnl=self.weekly_pnl,
            last_trade_time=self.last_trade_time,
            now=entry_time,
        )
        if not passed:
            self.rejected_decisions.append({"timestamp": entry_time.isoformat(), "reason": reason})
            return None

        sl_pct = decision.get("stop_loss_pct", self.profile.stop_loss_pct)
        tp_pct = decision.get("take_profit_pct", self.profile.take_profit_pct)
        if decision["action"] == "LONG":
            stop_loss = entry_price * (1 - sl_pct)
            take_profit = entry_price * (1 + tp_pct)
        else:
            stop_loss = entry_price * (1 + sl_pct)
            take_profit = entry_price * (1 - tp_pct)
        size = self.safety.calculate_size(
            decision,
            snapshot,
            equity=self.balance,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
        )
        if size <= 0:
            self.rejected_decisions.append({"timestamp": entry_time.isoformat(), "reason": "Calculated size <= 0"})
            return None

        pos = BacktestPosition(
            trade_id=f"BT-{entry_time.strftime('%Y%m%d%H%M')}-{len(self.closed_trades) + len(self.positions)}",
            action=decision["action"],
            entry_time=entry_time,
            entry_price=float(entry_price),
            size=float(size),
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
            conviction=int(decision.get("conviction", 0)),
            reasoning=decision.get("reasoning", ""),
            regime=snapshot.get("regime", {}).get("current_state", "UNKNOWN"),
        )
        self.positions.append(pos)
        self.last_trade_time = entry_time
        return pos

    def _gross_pnl(self, pos: BacktestPosition, exit_price: float) -> float:
        if pos.action == "LONG":
            return (exit_price - pos.entry_price) * pos.size
        return (pos.entry_price - exit_price) * pos.size

    def _net_pnl(self, pos: BacktestPosition, exit_price: float) -> float:
        if pos.action == "LONG":
            adjusted_entry = pos.entry_price * (1 + self.slippage_rate)
            adjusted_exit = exit_price * (1 - self.slippage_rate)
            gross = (adjusted_exit - adjusted_entry) * pos.size
        else:
            adjusted_entry = pos.entry_price * (1 - self.slippage_rate)
            adjusted_exit = exit_price * (1 + self.slippage_rate)
            gross = (adjusted_entry - adjusted_exit) * pos.size
        fees = (abs(adjusted_entry * pos.size) + abs(adjusted_exit * pos.size)) * self.fee_rate
        return gross - fees

    def close_position(self, pos: BacktestPosition, *, exit_time: pd.Timestamp, exit_price: float, reason: str):
        pnl = self._gross_pnl(pos, exit_price)
        if pos.action == "LONG":
            pnl_pct = (exit_price - pos.entry_price) / pos.entry_price if pos.entry_price else 0.0
        else:
            pnl_pct = (pos.entry_price - exit_price) / pos.entry_price if pos.entry_price else 0.0
        net_pnl = self._net_pnl(pos, exit_price)
        net_pnl_pct = net_pnl / self.initial_equity if self.initial_equity else 0.0
        trade = BacktestTrade(
            trade_id=pos.trade_id,
            action=pos.action,
            entry_time=pos.entry_time.isoformat(),
            exit_time=exit_time.isoformat(),
            entry_price=round(pos.entry_price, 8),
            exit_price=round(float(exit_price), 8),
            size=round(pos.size, 8),
            stop_loss=round(pos.stop_loss, 8),
            take_profit=round(pos.take_profit, 8),
            pnl=round(float(pnl), 8),
            pnl_pct=round(float(pnl_pct), 8),
            net_pnl=round(float(net_pnl), 8),
            net_pnl_pct=round(float(net_pnl_pct), 8),
            exit_reason=reason,
            conviction=pos.conviction,
            regime=pos.regime,
            reasoning=pos.reasoning,
        )
        self.closed_trades.append(trade)
        self.balance += pnl
        self.daily_pnl += pnl
        self.weekly_pnl += pnl
        self.positions = [p for p in self.positions if p.trade_id != pos.trade_id]

    def update_bar(self, bar: pd.Series):
        ts = pd.Timestamp(bar["timestamp"])
        self._roll_periods(ts)
        high = float(bar["high"])
        low = float(bar["low"])
        open_price = float(bar["open"])
        close_price = float(bar["close"])
        for pos in list(self.positions):
            exit_reason = None
            exit_price = None
            if pos.action == "LONG":
                stop_hit = low <= pos.stop_loss
                target_hit = high >= pos.take_profit
                if stop_hit:
                    exit_reason = "STOP_LOSS"
                    exit_price = pos.stop_loss
                elif target_hit:
                    exit_reason = "TAKE_PROFIT"
                    exit_price = pos.take_profit
            else:
                stop_hit = high >= pos.stop_loss
                target_hit = low <= pos.take_profit
                if stop_hit:
                    exit_reason = "STOP_LOSS"
                    exit_price = pos.stop_loss
                elif target_hit:
                    exit_reason = "TAKE_PROFIT"
                    exit_price = pos.take_profit
            if exit_reason:
                self.close_position(pos, exit_time=ts, exit_price=float(exit_price), reason=exit_reason)
                continue

            max_duration = pos.entry_time + pd.Timedelta(hours=self.profile.max_position_duration_hours)
            if ts >= max_duration:
                self.close_position(pos, exit_time=ts, exit_price=open_price, reason="MAX_DURATION")

        if self.daily_pnl < -self.profile.max_daily_loss * max(self.balance, self.initial_equity):
            for pos in list(self.positions):
                self.close_position(
                    pos,
                    exit_time=ts,
                    exit_price=close_price,
                    reason="DAILY_LOSS_CIRCUIT_BREAKER",
                )

    def mark_equity(self, price: float) -> float:
        equity = self.balance
        for pos in self.positions:
            equity += self._gross_pnl(pos, price)
        return equity

    def force_close_all(self, *, timestamp: pd.Timestamp, price: float):
        for pos in list(self.positions):
            self.close_position(pos, exit_time=timestamp, exit_price=price, reason="FORCED_FINAL_CLOSE")
