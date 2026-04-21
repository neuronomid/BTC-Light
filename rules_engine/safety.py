from typing import Dict, Optional
from dataclasses import dataclass
from config.settings import (
    MAX_RISK_PER_TRADE, MAX_DAILY_LOSS, MAX_WEEKLY_LOSS,
    MAX_OPEN_POSITIONS, MAX_POSITION_DURATION_HOURS,
    MIN_TIME_BETWEEN_TRADES_HOURS, MAX_LEVERAGE,
    MIN_CONVICTION_TO_TRADE, MIN_EV_TO_TRADE
)
from loguru import logger

@dataclass
class SafetyCheck:
    passed: bool
    reason: str

class SafetyEngine:
    def __init__(self):
        self.daily_pnl = 0.0
        self.weekly_pnl = 0.0
        self.open_positions = 0
        self.last_trade_time = None

    def check_all(
        self,
        decision: Dict,
        stats: Dict,
        equity: float = 10000.0
    ) -> SafetyCheck:
        if decision.get("action") == "NO_TRADE":
            return SafetyCheck(True, "No trade requested.")
        if decision.get("conviction", 0) < MIN_CONVICTION_TO_TRADE:
            return SafetyCheck(False, f"Conviction {decision.get('conviction')} < {MIN_CONVICTION_TO_TRADE}")
        prob = stats.get("probability", {})
        if prob.get("expected_value_per_trade", 0) < MIN_EV_TO_TRADE:
            return SafetyCheck(False, f"EV {prob.get('expected_value_per_trade')} < {MIN_EV_TO_TRADE}")
        cp = stats.get("change_point", {})
        if cp.get("recommend_halt", False):
            return SafetyCheck(False, "Change point detection recommends halt.")
        if self.open_positions >= MAX_OPEN_POSITIONS:
            return SafetyCheck(False, f"Max open positions {MAX_OPEN_POSITIONS} reached.")
        if self.daily_pnl < -MAX_DAILY_LOSS * equity:
            return SafetyCheck(False, f"Daily loss circuit breaker triggered: {self.daily_pnl}")
        if self.weekly_pnl < -MAX_WEEKLY_LOSS * equity:
            return SafetyCheck(False, f"Weekly loss circuit breaker triggered: {self.weekly_pnl}")
        return SafetyCheck(True, "All safety checks passed.")

    def calculate_size(
        self,
        decision: Dict,
        stats: Dict,
        equity: float = 10000.0,
        entry_price: float = 0.0,
        stop_loss_price: float = 0.0
    ) -> float:
        kelly = stats.get("probability", {}).get("kelly_fraction", 0)
        size = equity * min(kelly * 0.25, MAX_RISK_PER_TRADE) * decision.get("size_multiplier", 1.0)
        regime_stability = stats.get("change_point", {}).get("regime_stability_score", 1.0)
        size *= regime_stability
        if entry_price > 0 and stop_loss_price > 0:
            sl_dist = abs(entry_price - stop_loss_price)
            size = size * equity / sl_dist * MAX_LEVERAGE
        size = min(size, equity * MAX_RISK_PER_TRADE)
        return round(size, 6)
