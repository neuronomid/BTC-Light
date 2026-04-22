from typing import Dict, Optional
from dataclasses import dataclass
from config.settings import (
    MAX_RISK_PER_TRADE, MAX_DAILY_LOSS, MAX_WEEKLY_LOSS,
    MAX_OPEN_POSITIONS, MAX_POSITION_DURATION_HOURS,
    MIN_TIME_BETWEEN_TRADES_HOURS, MAX_LEVERAGE,
    MIN_CONVICTION_TO_TRADE, MIN_EV_TO_TRADE,
    KELLY_FRACTION,
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
        stop_loss_price: float = 0.0,
        max_risk_per_trade: float = MAX_RISK_PER_TRADE,
        max_leverage: float = MAX_LEVERAGE,
    ) -> float:
        # Futures sizing requires a known entry and stop loss to translate a
        # USD risk budget into BTC units. Without them, sizing is undefined.
        if equity <= 0 or entry_price <= 0 or stop_loss_price <= 0 or entry_price == stop_loss_price:
            return 0.0
        kelly = max(stats.get("probability", {}).get("kelly_fraction", 0) or 0.0, 0.0)
        stability = stats.get("change_point", {}).get("regime_stability_score", 1.0) or 1.0
        stability = max(0.0, min(stability, 1.0))
        multiplier = max(0.0, min(decision.get("size_multiplier", 1.0) or 1.0, 1.0))
        risk_fraction = min(kelly * KELLY_FRACTION, max_risk_per_trade) * stability * multiplier
        if risk_fraction <= 0:
            return 0.0
        risk_budget_usd = equity * risk_fraction
        sl_dist_usd = abs(entry_price - stop_loss_price)
        size_units = risk_budget_usd / sl_dist_usd
        # Hard notional cap: position notional must not exceed equity * max_leverage.
        max_notional_usd = equity * max(max_leverage, 0.0)
        max_size_units = max_notional_usd / entry_price
        size_units = min(size_units, max_size_units)
        return round(max(size_units, 0.0), 8)
