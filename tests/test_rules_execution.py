import unittest
from datetime import timedelta
from unittest.mock import patch

from rules_engine.execution import PaperExecutionEngine, Position
from rules_engine.safety import SafetyEngine
from shared.time_utils import utc_now


class FakeRedis:
    def __init__(self):
        self.published = []
        self.json_values = []

    def publish(self, channel, payload):
        self.published.append((channel, payload))

    def set_json(self, key, payload, ttl=None):
        self.json_values.append((key, payload, ttl))


def passing_snapshot():
    return {
        "symbol": "BTC-USD",
        "probability": {
            "expected_value_per_trade": 0.02,
            "kelly_fraction": 0.4,
        },
        "change_point": {
            "recommend_halt": False,
            "regime_stability_score": 1.0,
        },
    }


def long_decision(**overrides):
    data = {
        "action": "LONG",
        "conviction": 80,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.04,
        "size_multiplier": 1.0,
        "reasoning": "test decision",
    }
    data.update(overrides)
    return data


class TestSafetyEngine(unittest.TestCase):
    def test_no_trade_passes_without_other_checks(self):
        result = SafetyEngine().check_all({"action": "NO_TRADE"}, {}, equity=10_000)

        self.assertTrue(result.passed)
        self.assertEqual(result.reason, "No trade requested.")

    def test_low_conviction_fails(self):
        result = SafetyEngine().check_all(long_decision(conviction=20), passing_snapshot())

        self.assertFalse(result.passed)
        self.assertIn("Conviction", result.reason)

    def test_low_expected_value_fails(self):
        snapshot = passing_snapshot()
        snapshot["probability"]["expected_value_per_trade"] = 0.0

        result = SafetyEngine().check_all(long_decision(), snapshot)

        self.assertFalse(result.passed)
        self.assertIn("EV", result.reason)

    def test_change_point_halt_fails(self):
        snapshot = passing_snapshot()
        snapshot["change_point"]["recommend_halt"] = True

        result = SafetyEngine().check_all(long_decision(), snapshot)

        self.assertFalse(result.passed)
        self.assertIn("Change point", result.reason)

    def test_max_open_positions_fails(self):
        safety = SafetyEngine()
        safety.open_positions = 1

        result = safety.check_all(long_decision(), passing_snapshot())

        self.assertFalse(result.passed)
        self.assertIn("Max open positions", result.reason)

    def test_daily_and_weekly_loss_breakers_fail(self):
        safety = SafetyEngine()
        safety.daily_pnl = -501.0

        daily = safety.check_all(long_decision(), passing_snapshot(), equity=10_000)

        safety.daily_pnl = 0.0
        safety.weekly_pnl = -1001.0
        weekly = safety.check_all(long_decision(), passing_snapshot(), equity=10_000)

        self.assertFalse(daily.passed)
        self.assertIn("Daily loss", daily.reason)
        self.assertFalse(weekly.passed)
        self.assertIn("Weekly loss", weekly.reason)

    def test_all_checks_pass_for_valid_trade(self):
        result = SafetyEngine().check_all(long_decision(), passing_snapshot(), equity=10_000)

        self.assertTrue(result.passed)
        self.assertEqual(result.reason, "All safety checks passed.")

    def test_calculate_size_returns_zero_without_valid_prices(self):
        snapshot = passing_snapshot()
        snapshot["probability"]["kelly_fraction"] = 0.04
        snapshot["change_point"]["regime_stability_score"] = 0.5

        size = SafetyEngine().calculate_size(
            long_decision(size_multiplier=0.5),
            snapshot,
            equity=10_000,
        )

        self.assertEqual(size, 0.0)

    def test_calculate_size_converts_risk_budget_to_btc_units_with_stop_distance(self):
        size = SafetyEngine().calculate_size(
            long_decision(),
            passing_snapshot(),
            equity=10_000,
            entry_price=100.0,
            stop_loss_price=98.0,
        )

        # risk_budget = 10_000 * min(0.4 * 0.25, 0.02) = 200
        # size_units = 200 / (100 - 98) = 100
        self.assertEqual(size, 100.0)

    def test_calculate_size_enforces_leverage_cap_at_real_btc_prices(self):
        # Tiny stop distance relative to price; leverage cap binds instead.
        size = SafetyEngine().calculate_size(
            long_decision(),
            passing_snapshot(),
            equity=5_000,
            entry_price=100_000.0,
            stop_loss_price=99_999.0,
        )

        # max_notional = 5_000 * 5 = 25_000 -> max_size = 25_000 / 100_000 = 0.25
        self.assertAlmostEqual(size, 0.25, places=6)

    def test_calculate_size_produces_bounded_units_at_real_btc_prices(self):
        # On a $5K account, a 2% stop at $98,545 must not size anywhere near 100 BTC.
        size = SafetyEngine().calculate_size(
            long_decision(),
            passing_snapshot(),
            equity=5_000,
            entry_price=98_545.60,
            stop_loss_price=98_545.60 * (1 - 0.02),
        )

        # risk_budget = 5_000 * 0.02 = 100; sl_dist = 1970.912; size ~= 0.0507 BTC
        notional = size * 98_545.60
        self.assertLess(size, 0.1)
        self.assertLess(notional, 5_000 * 5 + 1e-6)
        self.assertAlmostEqual(size * 1970.912, 100.0, places=2)


class TestPaperExecutionEngine(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.redis_patch = patch("rules_engine.execution.redis_client", self.redis)
        self.redis_patch.start()
        self.addCleanup(self.redis_patch.stop)

    def test_update_price_marks_long_and_short_pnl(self):
        engine = PaperExecutionEngine()
        engine.positions = [
            Position("L1", "BTC-USD", "LONG", 100.0, 2.0, 95.0, 110.0, utc_now(), 80, "long"),
            Position("S1", "BTC-USD", "SHORT", 100.0, 3.0, 105.0, 90.0, utc_now(), 80, "short"),
        ]

        engine.update_price(110.0)

        self.assertEqual(engine.positions[0].pnl, 20.0)
        self.assertEqual(engine.positions[0].pnl_pct, 0.1)
        self.assertEqual(engine.positions[1].pnl, -30.0)
        self.assertEqual(engine.positions[1].pnl_pct, -0.1)

    def test_evaluate_decision_requires_current_price(self):
        engine = PaperExecutionEngine()

        pos = engine.evaluate_decision(passing_snapshot(), long_decision())

        self.assertIsNone(pos)
        self.assertEqual(self.redis.published, [])

    def test_evaluate_decision_opens_long_position_and_publishes_event(self):
        engine = PaperExecutionEngine(initial_equity=10_000)
        engine.update_price(100.0)

        pos = engine.evaluate_decision(passing_snapshot(), long_decision())

        self.assertIsNotNone(pos)
        self.assertEqual(pos.action, "LONG")
        self.assertEqual(pos.entry_price, 100.0)
        self.assertEqual(pos.stop_loss, 98.0)
        self.assertEqual(pos.take_profit, 104.0)
        self.assertEqual(pos.size, 100.0)
        self.assertEqual(engine.safety.open_positions, 1)
        self.assertEqual(self.redis.published[0][0], "position:opened")

    def test_evaluate_decision_respects_safety_failure(self):
        engine = PaperExecutionEngine()
        engine.update_price(100.0)

        pos = engine.evaluate_decision(passing_snapshot(), long_decision(conviction=10))

        self.assertIsNone(pos)
        self.assertEqual(engine.positions, [])
        self.assertEqual(self.redis.published, [])

    async def test_tick_closes_take_profit_and_updates_equity(self):
        engine = PaperExecutionEngine(initial_equity=10_000)
        callback_events = []

        async def on_position_closed(position, reason):
            callback_events.append((position.trade_id, reason, position.pnl))

        engine.on_position_closed = on_position_closed
        engine.update_price(100.0)
        pos = engine.evaluate_decision(passing_snapshot(), long_decision())
        self.assertIsNotNone(pos)

        engine.update_price(104.0)
        await engine.tick()

        self.assertEqual(pos.status, "CLOSED")
        self.assertEqual(len(engine.closed_trades), 1)
        self.assertEqual(engine.equity, 10_400.0)
        self.assertEqual(engine.daily_pnl, 400.0)
        self.assertEqual(callback_events, [(pos.trade_id, "TAKE_PROFIT", 400.0)])
        self.assertEqual(self.redis.published[-1][0], "position:closed")
        self.assertEqual(self.redis.published[-1][1]["reason"], "TAKE_PROFIT")

    async def test_tick_closes_stop_loss_for_short_position(self):
        engine = PaperExecutionEngine(initial_equity=10_000)
        engine.update_price(100.0)
        decision = long_decision(action="SHORT")
        pos = engine.evaluate_decision(passing_snapshot(), decision)
        self.assertIsNotNone(pos)

        engine.update_price(102.0)
        await engine.tick()

        self.assertEqual(pos.status, "CLOSED")
        self.assertEqual(engine.closed_trades[0].pnl, -200.0)
        self.assertEqual(self.redis.published[-1][1]["reason"], "STOP_LOSS")

    async def test_tick_closes_positions_that_exceed_max_duration(self):
        engine = PaperExecutionEngine()
        old_position = Position(
            "OLD",
            "BTC-USD",
            "LONG",
            100.0,
            1.0,
            50.0,
            200.0,
            utc_now() - timedelta(hours=30),
            80,
            "old",
        )
        engine.positions.append(old_position)
        engine.safety.open_positions = 1
        engine.update_price(101.0)

        await engine.tick()

        self.assertEqual(old_position.status, "CLOSED")
        self.assertEqual(self.redis.published[-1][1]["reason"], "MAX_DURATION")

    async def test_tick_applies_daily_loss_circuit_breaker_to_open_positions(self):
        engine = PaperExecutionEngine(initial_equity=10_000)
        position = Position(
            "CB",
            "BTC-USD",
            "LONG",
            100.0,
            1.0,
            1.0,
            1_000.0,
            utc_now(),
            80,
            "circuit breaker",
        )
        engine.positions.append(position)
        engine.safety.open_positions = 1
        engine.daily_pnl = -600.0
        engine.update_price(100.0)

        await engine.tick()

        self.assertEqual(position.status, "CLOSED")
        self.assertEqual(self.redis.published[-1][1]["reason"], "DAILY_LOSS_CIRCUIT_BREAKER")

    def test_get_status_counts_only_open_positions(self):
        engine = PaperExecutionEngine(initial_equity=10_000)
        engine.positions = [
            Position("OPEN", "BTC-USD", "LONG", 100, 1, 90, 110, utc_now(), 80, ""),
            Position("CLOSED", "BTC-USD", "LONG", 100, 1, 90, 110, utc_now(), 80, "", status="CLOSED"),
        ]
        engine.closed_trades = [engine.positions[1]]
        engine.update_price(101.234)

        status = engine.get_status()

        self.assertEqual(status["open_positions"], 1)
        self.assertEqual(status["closed_trades"], 1)
        self.assertEqual(status["current_price"], 101.234)


if __name__ == "__main__":
    unittest.main()
