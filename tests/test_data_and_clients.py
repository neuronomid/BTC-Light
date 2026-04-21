import json
import unittest
from unittest.mock import patch

import pandas as pd

from data.external_feeds import ExternalFeedManager
from data.ingest_yahoo import YahooFinanceIngestor
from shared.redis_client import RedisClient


class FakeTicker:
    def __init__(self, df):
        self.df = df
        self.calls = []

    def history(self, period, interval):
        self.calls.append((period, interval))
        return self.df.copy()


class FakeRedisLowLevel:
    def __init__(self):
        self.published = []
        self.set_values = []
        self.setex_values = []
        self.values = {}

    def publish(self, channel, payload):
        self.published.append((channel, payload))

    def set(self, key, payload):
        self.set_values.append((key, payload))
        self.values[key] = payload

    def setex(self, key, ttl, payload):
        self.setex_values.append((key, ttl, payload))
        self.values[key] = payload

    def get(self, key):
        return self.values.get(key)

    def pubsub(self):
        return "pubsub"


class FakeRedisFacade:
    def __init__(self):
        self.published = []
        self.json_values = []

    def publish(self, channel, payload):
        self.published.append((channel, payload))

    def set_json(self, key, payload, ttl=None):
        self.json_values.append((key, payload, ttl))


def hourly_history(rows=8):
    return pd.DataFrame(
        {
            "Open": [100 + i for i in range(rows)],
            "High": [101 + i for i in range(rows)],
            "Low": [99 + i for i in range(rows)],
            "Close": [100.5 + i for i in range(rows)],
            "Volume": [10 * (i + 1) for i in range(rows)],
            "Dividends": [0] * rows,
            "Stock Splits": [0] * rows,
        },
        index=pd.date_range("2024-01-01", periods=rows, freq="1h", tz="UTC", name="Datetime"),
    )


class TestYahooFinanceIngestor(unittest.IsolatedAsyncioTestCase):
    def make_ingestor(self, df=None):
        ingestor = YahooFinanceIngestor.__new__(YahooFinanceIngestor)
        ingestor.symbol = "BTC-USD"
        ingestor.interval = "1h"
        ingestor.ticker = FakeTicker(df if df is not None else hourly_history())
        return ingestor

    def test_fetch_recent_normalizes_yahoo_columns_and_timestamp(self):
        ingestor = self.make_ingestor()

        df = ingestor.fetch_recent(period="5d")

        self.assertEqual(ingestor.ticker.calls, [("5d", "1h")])
        self.assertIn("timestamp", df.columns)
        self.assertNotIn("stock_splits", df.columns)
        self.assertNotIn("dividends", df.columns)
        self.assertTrue(str(df["timestamp"].dt.tz).startswith("UTC"))
        self.assertEqual(df.iloc[0]["open"], 100)

    def test_fetch_recent_returns_empty_frame_unchanged(self):
        empty = pd.DataFrame()
        ingestor = self.make_ingestor(empty)

        df = ingestor.fetch_recent(period="1d")

        self.assertTrue(df.empty)

    def test_resample_to_4h_aggregates_ohlcv(self):
        ingestor = self.make_ingestor()
        df = ingestor.fetch_recent(period="1d")

        resampled = ingestor.resample_to_4h(df)

        self.assertEqual(len(resampled), 2)
        self.assertEqual(resampled.iloc[0]["open"], 100)
        self.assertEqual(resampled.iloc[0]["high"], 104)
        self.assertEqual(resampled.iloc[0]["low"], 99)
        self.assertEqual(resampled.iloc[0]["close"], 103.5)
        self.assertEqual(resampled.iloc[0]["volume"], 100)

    async def test_publish_latest_sends_candle_to_redis(self):
        redis = FakeRedisFacade()
        ingestor = self.make_ingestor()
        df = ingestor.fetch_recent(period="1d")

        with patch("data.ingest_yahoo.redis_client", redis):
            await ingestor.publish_latest(df)

        self.assertEqual(redis.published[0][0], "candles:new")
        self.assertEqual(redis.json_values[0][0], "latest_candle")
        self.assertEqual(redis.published[0][1]["symbol"], "BTC-USD")
        self.assertEqual(redis.published[0][1]["close"], 107.5)


class TestExternalFeedManager(unittest.TestCase):
    def test_fetch_symbol_normalizes_external_data(self):
        raw = hourly_history()

        with patch("data.external_feeds.yf.Ticker", return_value=FakeTicker(raw)) as ticker:
            df = ExternalFeedManager().fetch_symbol("btc_spx", "^GSPC", period="5d", interval="1h")

        ticker.assert_called_once_with("^GSPC")
        self.assertIn("timestamp", df.columns)
        self.assertNotIn("stock_splits", df.columns)
        self.assertEqual(df.iloc[-1]["close"], 107.5)

    def test_fetch_symbol_returns_none_when_yahoo_raises(self):
        class BrokenTicker:
            def history(self, period, interval):
                raise RuntimeError("network down")

        with patch("data.external_feeds.yf.Ticker", return_value=BrokenTicker()):
            df = ExternalFeedManager().fetch_symbol("btc_spx", "^GSPC")

        self.assertIsNone(df)

    def test_resample_all_to_4h_skips_empty_feeds(self):
        manager = ExternalFeedManager()
        manager.cache = {
            "btc_spx": YahooFinanceIngestor.__new__(YahooFinanceIngestor).resample_to_4h(
                self._normalized_history()
            ),
            "empty": pd.DataFrame(),
        }

        resampled = manager.resample_all_to_4h()

        self.assertEqual(list(resampled.keys()), ["btc_spx"])
        self.assertEqual(len(resampled["btc_spx"]), 2)

    def _normalized_history(self):
        df = hourly_history().reset_index()
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        return df.rename(columns={"datetime": "timestamp"}).drop(columns=["dividends", "stock_splits"])


class TestRedisClient(unittest.TestCase):
    def test_publish_serializes_payload_to_json(self):
        low_level = FakeRedisLowLevel()
        client = RedisClient()
        client._client = low_level

        client.publish("events", {"answer": 42})

        self.assertEqual(low_level.published, [("events", '{"answer": 42}')])

    def test_set_json_uses_set_or_setex_and_get_json_deserializes(self):
        low_level = FakeRedisLowLevel()
        client = RedisClient()
        client._client = low_level

        client.set_json("plain", {"a": 1})
        client.set_json("ttl", {"b": 2}, ttl=30)

        self.assertEqual(low_level.set_values[0][0], "plain")
        self.assertEqual(low_level.setex_values[0][0], "ttl")
        self.assertEqual(low_level.setex_values[0][1], 30)
        self.assertEqual(client.get_json("plain"), {"a": 1})
        self.assertEqual(json.loads(low_level.setex_values[0][2]), {"b": 2})

    def test_get_json_returns_none_for_missing_key(self):
        client = RedisClient()
        client._client = FakeRedisLowLevel()

        self.assertIsNone(client.get_json("missing"))

    def test_subscribe_returns_pubsub_after_subscribing(self):
        class PubSub:
            def __init__(self):
                self.channels = []

            def subscribe(self, channel):
                self.channels.append(channel)

        class RedisWithPubSub(FakeRedisLowLevel):
            def __init__(self):
                super().__init__()
                self.pubsub_instance = PubSub()

            def pubsub(self):
                return self.pubsub_instance

        low_level = RedisWithPubSub()
        client = RedisClient()
        client._client = low_level

        pubsub = client.subscribe("updates")

        self.assertIs(pubsub, low_level.pubsub_instance)
        self.assertEqual(pubsub.channels, ["updates"])


if __name__ == "__main__":
    unittest.main()
