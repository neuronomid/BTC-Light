import asyncio
import json
from datetime import datetime, timedelta
from typing import Awaitable, Callable, Dict, Optional, List
from dataclasses import dataclass, field
from shared.redis_client import redis_client
from shared.time_utils import utc_now
from rules_engine.safety import SafetyEngine, SafetyCheck
from config.settings import (
    MAX_RISK_PER_TRADE, MAX_DAILY_LOSS, MAX_WEEKLY_LOSS,
    MAX_OPEN_POSITIONS, MAX_POSITION_DURATION_HOURS,
    MIN_TIME_BETWEEN_TRADES_HOURS, MAX_LEVERAGE,
    MIN_CONVICTION_TO_TRADE, MIN_EV_TO_TRADE
)
from loguru import logger

@dataclass
class Position:
    trade_id: str
    symbol: str
    action: str
    entry_price: float
    size: float
    stop_loss: float
    take_profit: float
    opened_at: datetime
    conviction: int
    reasoning: str
    pnl: float = 0.0
    pnl_pct: float = 0.0
    status: str = "OPEN"
    closed_at: Optional[datetime] = None
    exit_reason: Optional[str] = None

class PaperExecutionEngine:
    def __init__(self, initial_equity: float = 10000.0):
        self.equity = initial_equity
        self.starting_equity = initial_equity
        self.positions: List[Position] = []
        self.closed_trades: List[Position] = []
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self.last_trade_time: Optional[datetime] = None
        self.safety = SafetyEngine()
        self.safety.open_positions = 0
        self.safety.daily_pnl = 0.0
        self.safety.weekly_pnl = 0.0
        self._running = False
        self._current_price: Optional[float] = None
        self.on_position_closed: Optional[Callable[[Position, str], Awaitable[None]]] = None

    def _generate_trade_id(self) -> str:
        return f"T-{utc_now().strftime('%Y%m%d%H%M%S')}-{len(self.positions)}"

    def update_price(self, price: float):
        self._current_price = price
        for pos in self.positions:
            if pos.status != "OPEN":
                continue
            if pos.action == "LONG":
                pos.pnl = (price - pos.entry_price) * pos.size
                pos.pnl_pct = (price - pos.entry_price) / pos.entry_price
            else:
                pos.pnl = (pos.entry_price - price) * pos.size
                pos.pnl_pct = (pos.entry_price - price) / pos.entry_price

    def _check_duration(self, pos: Position) -> bool:
        elapsed = utc_now() - pos.opened_at
        return elapsed > timedelta(hours=MAX_POSITION_DURATION_HOURS)

    def _check_sl_tp(self, pos: Position, price: float) -> Optional[str]:
        if pos.action == "LONG":
            if price <= pos.stop_loss:
                return "STOP_LOSS"
            if price >= pos.take_profit:
                return "TAKE_PROFIT"
        else:
            if price >= pos.stop_loss:
                return "STOP_LOSS"
            if price <= pos.take_profit:
                return "TAKE_PROFIT"
        return None

    async def _close_position(self, pos: Position, reason: str):
        pos.status = "CLOSED"
        pos.closed_at = utc_now()
        pos.exit_reason = reason
        self.closed_trades.append(pos)
        self.equity += pos.pnl
        self.daily_pnl += pos.pnl
        self.weekly_pnl += pos.pnl
        self.safety.daily_pnl = self.daily_pnl
        self.safety.weekly_pnl = self.weekly_pnl
        self.safety.open_positions -= 1
        logger.info(f"Closed {pos.trade_id} | {reason} | PnL: {pos.pnl:.2f} ({pos.pnl_pct*100:.2f}%)")
        if self.on_position_closed:
            try:
                await self.on_position_closed(pos, reason)
            except Exception as e:
                logger.error(f"Position close callback failed for {pos.trade_id}: {e}")
        redis_client.publish("position:closed", {
            "trade_id": pos.trade_id,
            "reason": reason,
            "pnl": pos.pnl,
            "pnl_pct": pos.pnl_pct,
            "equity": self.equity,
        })

    def evaluate_decision(self, snapshot: Dict, decision: Dict) -> Optional[Position]:
        if decision.get("action") == "NO_TRADE":
            return None
        if self.equity <= 0:
            logger.warning("Account insolvent (equity <= 0). Rejecting new trades.")
            return None
        check = self.safety.check_all(decision, snapshot, equity=self.equity)
        if not check.passed:
            logger.warning(f"Safety check failed: {check.reason}")
            return None
        if self._current_price is None:
            logger.warning("No current price available.")
            return None
        price = self._current_price
        sl_pct = decision.get("stop_loss_pct", 0.02)
        tp_pct = decision.get("take_profit_pct", 0.04)
        if decision["action"] == "LONG":
            sl = price * (1 - sl_pct)
            tp = price * (1 + tp_pct)
        else:
            sl = price * (1 + sl_pct)
            tp = price * (1 - tp_pct)
        size = self.safety.calculate_size(decision, snapshot, equity=self.equity, entry_price=price, stop_loss_price=sl)
        pos = Position(
            trade_id=self._generate_trade_id(),
            symbol=snapshot.get("symbol", "BTC-USD"),
            action=decision["action"],
            entry_price=price,
            size=size,
            stop_loss=sl,
            take_profit=tp,
            opened_at=utc_now(),
            conviction=decision.get("conviction", 0),
            reasoning=decision.get("reasoning", ""),
        )
        self.positions.append(pos)
        self.safety.open_positions += 1
        self.last_trade_time = utc_now()
        logger.info(f"Opened {pos.trade_id} | {pos.action} | Size: {pos.size:.6f} | Entry: {pos.entry_price:.2f}")
        redis_client.publish("position:opened", {
            "trade_id": pos.trade_id,
            "action": pos.action,
            "entry_price": pos.entry_price,
            "size": pos.size,
            "stop_loss": pos.stop_loss,
            "take_profit": pos.take_profit,
            "conviction": pos.conviction,
        })
        return pos

    async def tick(self):
        if self._current_price is None:
            return
        price = self._current_price
        for pos in list(self.positions):
            if pos.status != "OPEN":
                continue
            exit_reason = self._check_sl_tp(pos, price)
            if exit_reason:
                await self._close_position(pos, exit_reason)
                continue
            if self._check_duration(pos):
                await self._close_position(pos, "MAX_DURATION")
                continue
        if self.daily_pnl < -MAX_DAILY_LOSS * self.starting_equity:
            for pos in list(self.positions):
                if pos.status == "OPEN":
                    await self._close_position(pos, "DAILY_LOSS_CIRCUIT_BREAKER")
            logger.warning("Daily loss circuit breaker triggered. Halting.")

    async def run_loop(self, price_poll_interval: int = 10):
        self._running = True
        logger.info("Paper execution engine started.")
        while self._running:
            try:
                await self.tick()
            except Exception as e:
                logger.error(f"Execution tick error: {e}")
            await asyncio.sleep(price_poll_interval)

    def stop(self):
        self._running = False
        logger.info("Paper execution engine stopped.")

    def get_status(self) -> Dict:
        return {
            "equity": round(self.equity, 2),
            "starting_equity": round(self.starting_equity, 2),
            "open_positions": len([p for p in self.positions if p.status == "OPEN"]),
            "closed_trades": len(self.closed_trades),
            "daily_pnl": round(self.daily_pnl, 2),
            "weekly_pnl": round(self.weekly_pnl, 2),
            "current_price": self._current_price,
        }
