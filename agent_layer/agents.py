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
        regime = stats.get("regime", {}) or {}
        trend = stats.get("trend", {}) or {}
        efficiency = stats.get("efficiency", {}) or {}
        volatility = stats.get("volatility", {}) or {}

        state = regime.get("current_state", "")
        state_conf = float(regime.get("state_confidence", 0.6) or 0.6)
        trend_strength = float(trend.get("trend_strength_score", 0.5) or 0.5)
        hurst = float(trend.get("hurst_100", 0.5) or 0.5)
        adx = float(trend.get("adx", 0.0) or 0.0)
        classification = trend.get("trend_classification", "")
        eff_ratio = efficiency.get("efficiency_ratio")
        if eff_ratio is None:
            eff_ratio = efficiency.get("kaufman_efficiency_ratio", 0.0)
        eff_ratio = float(eff_ratio or 0.0)
        vol_percentile = float(volatility.get("vol_percentile", 0.5) or 0.5)

        action = "NO_TRADE"
        conviction = 50
        reasoning = f"Mock decision based on {state}"

        # Trend-following: HMM trend regime is the primary directional cue.
        # The old logic also required trend_classification == TRENDING, which
        # hard-gated on hurst>0.55 AND adx>25 and almost never fired in
        # practice. We now trade the regime direction as long as HMM
        # confidence or trend strength confirms it, and only step aside when
        # both are clearly weak.
        if state in ("BULL_TREND", "BEAR_TREND"):
            direction_action = "LONG" if state == "BULL_TREND" else "SHORT"
            if state_conf < 0.35 and trend_strength < 0.2 and adx < 15:
                action = "NO_TRADE"
                conviction = 50
                reasoning = f"{state} but low confidence (conf={state_conf:.2f}, strength={trend_strength:.2f})"
            else:
                action = direction_action
                raw = 70 + 15 * max(state_conf, 0.5) + 10 * trend_strength + 5 * min(adx / 40.0, 1.0)
                conviction = int(round(max(70, min(95, raw))))
                reasoning = (
                    f"{state}: state_conf={state_conf:.2f}, trend_strength={trend_strength:.2f}, "
                    f"adx={adx:.1f}, hurst={hurst:.2f}"
                )
        # Mean-reversion in low-vol range when statistics clearly indicate it.
        # Direction comes from short-term price-vs-regime-mean via efficiency:
        # negative eff_ratio (downtrend exhausted in range) -> LONG rebound,
        # positive eff_ratio (uptrend exhausted in range) -> SHORT rebound.
        elif (
            state == "LOW_VOL_RANGE"
            and classification == "MEAN_REVERTING"
            and hurst < 0.45
            and abs(eff_ratio) > 0.15
            and vol_percentile < 0.7
        ):
            action = "SHORT" if eff_ratio > 0 else "LONG"
            raw = 70 + 10 * (0.5 - hurst) * 2 + 10 * min(abs(eff_ratio), 1.0)
            conviction = int(round(max(70, min(85, raw))))
            reasoning = (
                f"Mean-reversion in LOW_VOL_RANGE: hurst={hurst:.2f}, "
                f"eff_ratio={eff_ratio:.2f}"
            )

        return TradeDecisionOutput(
            action=action,
            conviction=conviction,
            entry_zone={"low": 0.0, "high": 0.0},
            stop_loss_pct=0.02,
            take_profit_pct=0.05,
            invalidation_conditions=[],
            size_multiplier=1.0,
            reasoning=reasoning,
            statistical_signals_weighted={"hmm": 0.3, "hurst": 0.2, "vol": 0.2, "tail": 0.1, "eff": 0.2},
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
