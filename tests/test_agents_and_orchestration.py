import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agent_layer.agents import (
    MockAgentLayer,
    NewsSentimentOutput,
    TradeDecisionOutput,
)
from agent_layer.openrouter_agents import OpenRouterAgentLayer
from orchestrator import TradingOrchestrator
from statistical_engine.engine import StatisticalEngine


class FakeRedis:
    def __init__(self):
        self.client = SimpleNamespace(set=self._set)
        self.set_calls = []
        self.published = []
        self.json_values = []

    def _set(self, key, value):
        self.set_calls.append((key, value))

    def publish(self, channel, payload):
        self.published.append((channel, payload))

    def set_json(self, key, payload, ttl=None):
        self.json_values.append((key, payload, ttl))


class TestAgentLayer(unittest.TestCase):
    def test_mock_agent_creates_long_and_short_decisions_from_regime_and_trend(self):
        agents = MockAgentLayer()
        bull_stats = {"regime": {"current_state": "BULL_TREND"}, "trend": {"trend_classification": "TRENDING"}}
        bear_stats = {"regime": {"current_state": "BEAR_TREND"}, "trend": {"trend_classification": "TRENDING"}}
        range_stats = {"regime": {"current_state": "LOW_VOL_RANGE"}, "trend": {"trend_classification": "RANDOM_WALK"}}

        self.assertEqual(agents.trade_decision(bull_stats, {}, {}).action, "LONG")
        self.assertEqual(agents.trade_decision(bear_stats, {}, {}).action, "SHORT")
        self.assertEqual(agents.trade_decision(range_stats, {}, {}).action, "NO_TRADE")

    def test_mock_agent_outputs_validate_expected_ranges(self):
        agents = MockAgentLayer()
        stats = {"regime": {"current_state": "BULL_TREND", "state_confidence": 0.85}}

        context = agents.market_context(stats)
        news = agents.news_sentiment(stats)
        risk = agents.risk_monitor({}, {"change_point": {"recommend_halt": True}})

        self.assertEqual(context.statistical_coherence_score, 0.85)
        self.assertEqual(news.news_sentiment_score, 0.0)
        self.assertTrue(risk.regime_shift_detected)

    def test_trade_decision_model_rejects_invalid_conviction_and_size_multiplier(self):
        with self.assertRaises(ValueError):
            TradeDecisionOutput(
                action="LONG",
                conviction=101,
                entry_zone={"low": 1.0, "high": 2.0},
                stop_loss_pct=0.02,
                take_profit_pct=0.04,
                invalidation_conditions=[],
                size_multiplier=1.0,
                reasoning="bad conviction",
                statistical_signals_weighted={},
            )

        with self.assertRaises(ValueError):
            TradeDecisionOutput(
                action="LONG",
                conviction=80,
                entry_zone={"low": 1.0, "high": 2.0},
                stop_loss_pct=0.02,
                take_profit_pct=0.04,
                invalidation_conditions=[],
                size_multiplier=2.0,
                reasoning="bad size",
                statistical_signals_weighted={},
            )

    def test_openrouter_agent_parses_json_fenced_market_context(self):
        layer = OpenRouterAgentLayer.__new__(OpenRouterAgentLayer)
        layer.model_opus = "opus"
        layer.model_sonnet = "sonnet"
        raw = """```json
{
  "regime_interpretation": "BULL_TREND",
  "narrative": "trend up",
  "key_levels": {"support": [100.0], "resistance": [120.0]},
  "statistical_coherence_score": 0.8,
  "notable_divergences": [],
  "context_summary": "constructive"
}
```"""

        with patch.object(OpenRouterAgentLayer, "_call", return_value=raw):
            context = layer.market_context({"symbol": "BTC-USD"}, price_data={"close": 110})

        self.assertEqual(context.regime_interpretation, "BULL_TREND")
        self.assertEqual(context.key_levels["support"], [100.0])

    def test_openrouter_agent_parses_plain_json_news_sentiment(self):
        layer = OpenRouterAgentLayer.__new__(OpenRouterAgentLayer)
        layer.model_opus = "opus"
        layer.model_sonnet = "sonnet"
        raw = """{
  "news_sentiment_score": -0.2,
  "directional_bias": "BEARISH",
  "confidence": 0.7,
  "key_events": [],
  "black_swan_risk": "MEDIUM",
  "macro_events_next_24h": ["FOMC"]
}"""

        with patch.object(OpenRouterAgentLayer, "_call", return_value=raw):
            news = layer.news_sentiment({"symbol": "BTC-USD"}, headlines=[])

        self.assertEqual(news.directional_bias, "BEARISH")
        self.assertEqual(news.macro_events_next_24h, ["FOMC"])


class TestStatisticalEngineOrchestration(unittest.IsolatedAsyncioTestCase):
    def test_run_all_requires_loaded_data(self):
        with self.assertRaises(RuntimeError):
            StatisticalEngine().run_all()

    def test_run_all_builds_snapshot_from_component_outputs(self):
        import pandas as pd

        df = pd.DataFrame(
            {
                "close": [100.0, 101.0, 102.5],
                "high": [101.0, 102.0, 103.0],
                "low": [99.0, 100.0, 101.5],
                "volume": [1000.0, 1100.0, 1200.0],
            }
        )
        engine = StatisticalEngine()
        engine._df = df

        class FakeRegime:
            def __init__(self):
                self.fit_called = False

            def fit(self, value):
                self.fit_called = True

            def predict(self, value):
                return {"current_state": "BULL_TREND", "state_confidence": 0.9}

        class FakeVol:
            def __init__(self):
                self.fit_called = False

            def fit(self, value):
                self.fit_called = True

            def forecast(self, value):
                return {"garch_forecast_4h": 0.01}

        engine.regime = FakeRegime()
        engine.vol = FakeVol()
        engine.trend = SimpleNamespace(analyze=lambda value: {"trend_classification": "TRENDING"})
        engine.cp = SimpleNamespace(detect=lambda value: {"recommend_halt": False})
        engine.tail = SimpleNamespace(analyze=lambda value: {"tail_risk_level": "LOW"})
        engine.eff = SimpleNamespace(analyze=lambda value: {"efficiency_score": 0.8})
        engine.corr = SimpleNamespace(analyze=lambda value, external=None: {"risk_on_off_regime": "MIXED"})

        snapshot = engine.run_all()

        self.assertTrue(engine.regime.fit_called)
        self.assertTrue(engine.vol.fit_called)
        self.assertEqual(snapshot["latest_close"], 102.5)
        self.assertEqual(snapshot["regime"]["current_state"], "BULL_TREND")
        self.assertEqual(snapshot["volatility"]["garch_forecast_4h"], 0.01)

    async def test_refresh_data_fetches_external_when_requested(self):
        import pandas as pd

        df = pd.DataFrame({"close": [1.0], "volume": [1.0]})
        engine = StatisticalEngine()
        engine.ingestor = SimpleNamespace(run_once=lambda: None)

        async def run_once():
            return df

        engine.ingestor.run_once = run_once

        class FakeExternal:
            def __init__(self):
                self.fetched = False

            def fetch_all(self):
                self.fetched = True

            def resample_all_to_4h(self):
                return {"btc_spx": df}

        engine.external = FakeExternal()

        result = await engine.refresh_data(fetch_external=True)

        self.assertIs(result, df)
        self.assertTrue(engine.external.fetched)
        self.assertEqual(engine._external_df, {"btc_spx": df})

    def test_evaluate_trade_passes_regime_drift_and_garch_vol_to_probability_engine(self):
        import pandas as pd

        engine = StatisticalEngine()
        engine._df = pd.DataFrame({"close": [100.0, 101.0]})
        engine.vol = SimpleNamespace(forecast=lambda df: {"garch_forecast_4h": 0.03})
        engine.regime = SimpleNamespace(predict=lambda df: {"current_state": "BEAR_TREND"})

        class FakeProbability:
            def evaluate_trade(self, df, direction, sl_pct, tp_pct, garch_vol=None, regime_drift=0.0):
                self.args = (df, direction, sl_pct, tp_pct, garch_vol, regime_drift)
                return {"expected_value_per_trade": 0.01}

        engine.prob = FakeProbability()

        result = engine.evaluate_trade("SHORT", 0.02, 0.04)

        self.assertEqual(result, {"expected_value_per_trade": 0.01})
        self.assertEqual(engine.prob.args[1:], ("SHORT", 0.02, 0.04, 0.03, -0.001))

    async def test_publish_sends_snapshot_to_redis(self):
        redis = FakeRedis()
        snapshot = {"symbol": "BTC-USD"}

        with patch("statistical_engine.engine.redis_client", redis):
            await StatisticalEngine().publish(snapshot)

        self.assertEqual(redis.published, [("statistical:snapshot", snapshot)])
        self.assertEqual(redis.json_values, [("latest_statistical_snapshot", snapshot, 3600)])


class TestTradingOrchestrator(unittest.IsolatedAsyncioTestCase):
    async def test_cycle_runs_engine_agents_probability_execution_and_status_publish(self):
        redis = FakeRedis()
        orchestrator = TradingOrchestrator()

        class FakeEngine:
            async def run_cycle(self, fetch_external=False):
                self.fetch_external = fetch_external
                return {
                    "symbol": "BTC-USD",
                    "latest_close": 100.0,
                    "regime": {"current_state": "BULL_TREND", "state_confidence": 0.8},
                    "trend": {"trend_classification": "TRENDING"},
                }

            def evaluate_trade(self, action, sl_pct, tp_pct):
                self.trade_args = (action, sl_pct, tp_pct)
                return {"expected_value_per_trade": 0.02, "kelly_fraction": 0.4}

        class FakeAgents:
            def market_context(self, snapshot):
                return SimpleNamespace(model_dump=lambda: {"context": "ok"})

            def news_sentiment(self, snapshot):
                return NewsSentimentOutput(
                    news_sentiment_score=0.0,
                    directional_bias="NEUTRAL",
                    confidence=0.5,
                    key_events=[],
                    black_swan_risk="LOW",
                    macro_events_next_24h=[],
                )

            def trade_decision(self, snapshot, context, news):
                return TradeDecisionOutput(
                    action="LONG",
                    conviction=80,
                    entry_zone={"low": 99.0, "high": 101.0},
                    stop_loss_pct=0.02,
                    take_profit_pct=0.04,
                    invalidation_conditions=[],
                    size_multiplier=1.0,
                    reasoning="trend",
                    statistical_signals_weighted={},
                )

        class FakeExecution:
            def __init__(self):
                self.updated_price = None
                self.evaluated = None
                self.ticked = False

            def update_price(self, price):
                self.updated_price = price

            def evaluate_decision(self, snapshot, decision):
                self.evaluated = (snapshot, decision)
                return "position"

            async def tick(self):
                self.ticked = True

            def get_status(self):
                return {"equity": 10_000.0, "open_positions": 1, "daily_pnl": 0.0}

        orchestrator.engine = FakeEngine()
        orchestrator.execution = FakeExecution()
        orchestrator._agents = FakeAgents()

        with patch("orchestrator.redis_client", redis):
            await orchestrator._cycle()

        self.assertEqual(orchestrator.execution.updated_price, 100.0)
        self.assertEqual(orchestrator.engine.trade_args, ("LONG", 0.02, 0.04))
        self.assertEqual(redis.set_calls, [("latest_price", "100.0")])
        self.assertEqual(redis.published[0][0], "trade_decision")
        self.assertEqual(redis.json_values[0][0], "trading_status")
        self.assertTrue(orchestrator.execution.ticked)
        self.assertEqual(orchestrator.execution.evaluated[1]["action"], "LONG")


if __name__ == "__main__":
    unittest.main()
