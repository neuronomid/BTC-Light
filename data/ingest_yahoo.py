import asyncio
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select
from shared.db import AsyncSessionLocal, Candle, init_db
from shared.redis_client import redis_client
from config.settings import SYMBOL, YF_INTERVAL, LOOKBACK_DAYS, TIMEFRAME
from loguru import logger

class YahooFinanceIngestor:
    def __init__(self, symbol: str = SYMBOL, interval: str = YF_INTERVAL):
        self.symbol = symbol
        self.interval = interval
        self.ticker = yf.Ticker(symbol)

    def fetch_recent(self, period: str = "60d", interval: Optional[str] = None) -> pd.DataFrame:
        iv = interval or self.interval
        logger.info(f"Fetching {self.symbol} data (period={period}, interval={iv})")
        df = self.ticker.history(period=period, interval=iv)
        if df.empty:
            logger.warning("No data returned from Yahoo Finance.")
            return df
        df = df.reset_index()
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        if "datetime" in df.columns:
            df = df.rename(columns={"datetime": "timestamp"})
        if "stock_splits" in df.columns:
            df = df.drop(columns=["stock_splits", "dividends"], errors="ignore")
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        logger.info(f"Fetched {len(df)} rows.")
        return df

    def resample_to_4h(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.set_index("timestamp")
        ohlc = df.resample("4h").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        }).dropna()
        ohlc = ohlc.reset_index()
        logger.info(f"Resampled to 4H: {len(ohlc)} candles.")
        return ohlc

    async def store_candles(self, df: pd.DataFrame):
        if df.empty:
            return
        async with AsyncSessionLocal() as session:
            count = 0
            for _, row in df.iterrows():
                ts_raw = pd.to_datetime(row["timestamp"])
                if ts_raw.tzinfo is not None:
                    ts_raw = ts_raw.tz_localize(None)
                ts = ts_raw.to_pydatetime()
                existing = await session.execute(
                    select(Candle).where(
                        Candle.symbol == self.symbol,
                        Candle.timeframe == TIMEFRAME,
                        Candle.timestamp == ts
                    )
                )
                if existing.scalar_one_or_none() is None:
                    candle = Candle(
                        symbol=self.symbol,
                        timeframe=TIMEFRAME,
                        timestamp=ts,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["volume"])
                    )
                    session.add(candle)
                    count += 1
            await session.commit()
            logger.info(f"Stored {count} new candles.")

    async def publish_latest(self, df: pd.DataFrame):
        if df.empty:
            return
        latest = df.iloc[-1]
        payload = {
            "symbol": self.symbol,
            "timeframe": TIMEFRAME,
            "timestamp": str(latest["timestamp"]),
            "open": float(latest["open"]),
            "high": float(latest["high"]),
            "low": float(latest["low"]),
            "close": float(latest["close"]),
            "volume": float(latest["volume"]),
        }
        redis_client.publish("candles:new", payload)
        redis_client.set_json("latest_candle", payload)
        logger.info(f"Published latest candle {payload['timestamp']}")

    async def run_once(self):
        df = self.fetch_recent(period=f"{LOOKBACK_DAYS}d")
        if TIMEFRAME == "4h":
            df = self.resample_to_4h(df)
        await self.store_candles(df)
        await self.publish_latest(df)
        return df

    async def run_loop(self, interval_seconds: int = 300):
        while True:
            try:
                await self.run_once()
            except Exception as e:
                logger.error(f"Ingestion error: {e}")
            await asyncio.sleep(interval_seconds)

async def main():
    await init_db()
    ingestor = YahooFinanceIngestor()
    await ingestor.run_once()

if __name__ == "__main__":
    asyncio.run(main())
