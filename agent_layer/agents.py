import json
from typing import Dict, Optional
from pydantic import BaseModel, Field
from loguru import logger

class MarketContextOutput(BaseModel):
    regime_interpretation: str
    narrative: str
    key_levels: Dict
    statistical_coherence_score: float = Field(ge=0.0, le=1.0)
    notable_divergences: list
    context_summary: str

class NewsSentimentOutput(BaseModel):
    news_sentiment_score: float = Field(ge=-1.0, le=1.0)
    directional_bias: str
    confidence: float = Field(ge=0.0, le=1.0)
    key_events: list
    black_swan_risk: str
    macro_events_next_24h: list

class TradeDecisionOutput(BaseModel):
    action: str
    conviction: int = Field(ge=0, le=100)
    entry_zone: Dict[str, float]
    stop_loss_pct: float
    take_profit_pct: float
    invalidation_conditions: list
    size_multiplier: float = Field(ge=0.0, le=1.5)
    reasoning: str
    statistical_signals_weighted: Dict[str, float]

class RiskMonitorOutput(BaseModel):
    thesis_still_valid: bool
    regime_shift_detected: bool
    recommend_action: str
    urgency: str
    reasoning: str

class MockAgentLayer:
    def __init__(self):
        pass

    def market_context(self, stats: Dict) -> MarketContextOutput:
        regime = stats.get("regime", {})
        trend = stats.get("trend", {})
        state = regime.get("current_state", "UNKNOWN")
        narrative = f"Market is in {state}."
        coherence = regime.get("state_confidence", 0.5)
        return MarketContextOutput(
            regime_interpretation=state,
            narrative=narrative,
            key_levels={"support": [], "resistance": []},
            statistical_coherence_score=coherence,
            notable_divergences=[],
            context_summary=narrative
        )

    def news_sentiment(self, stats: Dict) -> NewsSentimentOutput:
        return NewsSentimentOutput(
            news_sentiment_score=0.0,
            directional_bias="NEUTRAL",
            confidence=0.5,
            key_events=[],
            black_swan_risk="LOW",
            macro_events_next_24h=[]
        )

    def trade_decision(self, stats: Dict, context: Dict, news: Dict) -> TradeDecisionOutput:
        regime = stats.get("regime", {})
        trend = stats.get("trend", {})
        state = regime.get("current_state", "")
        action = "NO_TRADE"
        conviction = 50
        if state == "BULL_TREND" and trend.get("trend_classification") == "TRENDING":
            action = "LONG"
            conviction = 75
        elif state == "BEAR_TREND" and trend.get("trend_classification") == "TRENDING":
            action = "SHORT"
            conviction = 75
        return TradeDecisionOutput(
            action=action,
            conviction=conviction,
            entry_zone={"low": 0.0, "high": 0.0},
            stop_loss_pct=0.02,
            take_profit_pct=0.04,
            invalidation_conditions=[],
            size_multiplier=1.0,
            reasoning=f"Mock decision based on {state}",
            statistical_signals_weighted={"hmm": 0.3, "hurst": 0.2, "vol": 0.2, "tail": 0.1, "eff": 0.2}
        )

    def risk_monitor(self, position: Dict, stats: Dict) -> RiskMonitorOutput:
        cp = stats.get("change_point", {})
        return RiskMonitorOutput(
            thesis_still_valid=True,
            regime_shift_detected=cp.get("recommend_halt", False),
            recommend_action="HOLD",
            urgency="LOW",
            reasoning="No immediate risk flags."
        )
