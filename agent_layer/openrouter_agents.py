import json
from typing import Dict, Optional
from openai import OpenAI
from config.settings import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, AGENT_MODEL_OPUS, AGENT_MODEL_SONNET
from loguru import logger


class MarketContextOutput:
    def __init__(self, regime_interpretation: str, narrative: str, key_levels: Dict,
                 statistical_coherence_score: float, notable_divergences: list, context_summary: str):
        self.regime_interpretation = regime_interpretation
        self.narrative = narrative
        self.key_levels = key_levels
        self.statistical_coherence_score = statistical_coherence_score
        self.notable_divergences = notable_divergences
        self.context_summary = context_summary

    def model_dump(self):
        return self.__dict__


class NewsSentimentOutput:
    def __init__(self, news_sentiment_score: float, directional_bias: str, confidence: float,
                 key_events: list, black_swan_risk: str, macro_events_next_24h: list):
        self.news_sentiment_score = news_sentiment_score
        self.directional_bias = directional_bias
        self.confidence = confidence
        self.key_events = key_events
        self.black_swan_risk = black_swan_risk
        self.macro_events_next_24h = macro_events_next_24h

    def model_dump(self):
        return self.__dict__


class TradeDecisionOutput:
    def __init__(self, action: str, conviction: int, entry_zone: Dict[str, float],
                 stop_loss_pct: float, take_profit_pct: float, invalidation_conditions: list,
                 size_multiplier: float, reasoning: str, statistical_signals_weighted: Dict[str, float]):
        self.action = action
        self.conviction = conviction
        self.entry_zone = entry_zone
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.invalidation_conditions = invalidation_conditions
        self.size_multiplier = size_multiplier
        self.reasoning = reasoning
        self.statistical_signals_weighted = statistical_signals_weighted

    def model_dump(self):
        return self.__dict__


class RiskMonitorOutput:
    def __init__(self, thesis_still_valid: bool, regime_shift_detected: bool,
                 recommend_action: str, urgency: str, reasoning: str):
        self.thesis_still_valid = thesis_still_valid
        self.regime_shift_detected = regime_shift_detected
        self.recommend_action = recommend_action
        self.urgency = urgency
        self.reasoning = reasoning


class OpenRouterAgentLayer:
    def __init__(self):
        if not OPENROUTER_API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY not set in environment.")
        self.client = OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=OPENROUTER_API_KEY,
        )
        self.model_opus = AGENT_MODEL_OPUS
        self.model_sonnet = AGENT_MODEL_SONNET

    def _call(self, model: str, system: str, messages: list, max_tokens: int = 2048) -> str:
        try:
            resp = self.client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}] + messages,
                max_tokens=max_tokens,
            )
            return resp.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenRouter API error: {e}")
            raise

    def _extract_json(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        return text.strip()

    def market_context(self, stats: Dict, price_data: Dict = None) -> MarketContextOutput:
        system = (
            "You are a senior quantitative market analyst. Interpret statistical outputs for BTC-USD on the 4H timeframe. "
            "Output ONLY valid JSON matching this schema:\n"
            '{"regime_interpretation":"string","narrative":"string","key_levels":{"support":[float],"resistance":[float]},'
            '"statistical_coherence_score":0.0-1.0,"notable_divergences":["string"],"context_summary":"string"}'
        )
        prompt = f"""Statistical Engine Output:
{json.dumps(stats, indent=2)}

Latest Price: {json.dumps(price_data or {})}

Provide your JSON interpretation."""
        raw = self._call(self.model_opus, system, [{"role": "user", "content": prompt}])
        text = self._extract_json(raw)
        data = json.loads(text)
        return MarketContextOutput(**data)

    def news_sentiment(self, stats: Dict, headlines: list = None) -> NewsSentimentOutput:
        system = (
            "You are a crypto news analyst. Assess directional bias from market context and any headlines provided. "
            "Output ONLY valid JSON matching this schema:\n"
            '{"news_sentiment_score":-1.0 to 1.0,"directional_bias":"BULLISH|BEARISH|NEUTRAL","confidence":0.0-1.0,'
            '"key_events":[{"headline":"string","impact":"string"}],"black_swan_risk":"LOW|MEDIUM|HIGH",'
            '"macro_events_next_24h":["string"]}'
        )
        prompt = f"""Statistical Context:
{json.dumps(stats, indent=2)}

Headlines: {json.dumps(headlines or [])}

Provide your JSON assessment."""
        raw = self._call(self.model_sonnet, system, [{"role": "user", "content": prompt}])
        text = self._extract_json(raw)
        data = json.loads(text)
        return NewsSentimentOutput(**data)

    def trade_decision(
        self,
        stats: Dict,
        context: MarketContextOutput,
        news: NewsSentimentOutput,
        recent_trades: list = None
    ) -> TradeDecisionOutput:
        system = (
            "You are a disciplined crypto futures trader. Make a directional trade decision based on statistical and qualitative inputs. "
            "Output ONLY valid JSON matching this schema:\n"
            '{"action":"LONG|SHORT|NO_TRADE","conviction":0-100,"entry_zone":{"low":float,"high":float},'
            '"stop_loss_pct":float,"take_profit_pct":float,"invalidation_conditions":["string"],'
            '"size_multiplier":0.0-1.5,"reasoning":"string","statistical_signals_weighted":{"hmm":float,"hurst":float,...}}'
        )
        prompt = f"""Statistical Engine:
{json.dumps(stats, indent=2)}

Market Context:
{json.dumps(context.__dict__, indent=2)}

News/Sentiment:
{json.dumps(news.__dict__, indent=2)}

Recent Trades:
{json.dumps(recent_trades or [])}

Rules: conviction >= 70 required to trade. EV must be positive. Be honest about uncertainty.

Provide your JSON decision."""
        raw = self._call(self.model_opus, system, [{"role": "user", "content": prompt}])
        text = self._extract_json(raw)
        data = json.loads(text)
        return TradeDecisionOutput(**data)

    def risk_monitor(self, position: Dict, stats: Dict, news: NewsSentimentOutput = None) -> RiskMonitorOutput:
        system = (
            "You are a risk manager monitoring an open BTC futures position. "
            "Output ONLY valid JSON matching this schema:\n"
            '{"thesis_still_valid":bool,"regime_shift_detected":bool,"recommend_action":"HOLD|EXIT_MARKET|TIGHTEN_STOP|TAKE_PARTIAL",'
            '"urgency":"LOW|MEDIUM|HIGH","reasoning":"string"}'
        )
        prompt = f"""Position:
{json.dumps(position, indent=2)}

Current Statistical Snapshot:
{json.dumps(stats, indent=2)}

News Context:
{json.dumps(news.__dict__ if news else {}, indent=2)}

Provide your JSON risk assessment."""
        raw = self._call(self.model_sonnet, system, [{"role": "user", "content": prompt}])
        text = self._extract_json(raw)
        data = json.loads(text)
        return RiskMonitorOutput(**data)
