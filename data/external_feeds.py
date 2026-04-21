import asyncio
import yfinance as yf
import pandas as pd
from typing import Dict, Optional
from data.ingest_yahoo import YahooFinanceIngestor
from loguru import logger

EXTERNAL_SYMBOLS = {
    "btc_spx": "^GSPC",
    "btc_dxy": "UUP",
    "btc_gold": "GC=F",
    "btc_eth": "ETH-USD",
}

class ExternalFeedManager:
    def __init__(self):
        self.cache: Dict[str, pd.DataFrame] = {}

    def fetch_symbol(self, key: str, symbol: str, period: str = "60d", interval: str = "1h") -> Optional[pd.DataFrame]:
        logger.info(f"Fetching external feed {key}: {symbol}")
        ticker = yf.Ticker(symbol)
        try:
            df = ticker.history(period=period, interval=interval)
            if df.empty:
                logger.warning(f"No data for {symbol}")
                return None
            df = df.reset_index()
            df.columns = [c.lower().replace(" ", "_") for c in df.columns]
            if "datetime" in df.columns:
                df = df.rename(columns={"datetime": "timestamp"})
            df = df.drop(columns=["stock_splits", "dividends"], errors="ignore")
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
            logger.info(f"Fetched {len(df)} rows for {symbol}")
            return df
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return None

    def fetch_all(self, period: str = "60d", interval: str = "1h") -> Dict[str, pd.DataFrame]:
        for key, symbol in EXTERNAL_SYMBOLS.items():
            df = self.fetch_symbol(key, symbol, period, interval)
            if df is not None:
                self.cache[key] = df
        return self.cache

    def resample_all_to_4h(self) -> Dict[str, pd.DataFrame]:
        resampled = {}
        for key, df in self.cache.items():
            if df is None or df.empty:
                continue
            df = df.set_index("timestamp")
            ohlc = df.resample("4h").agg({
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum"
            }).dropna()
            ohlc = ohlc.reset_index()
            resampled[key] = ohlc
            logger.info(f"Resampled {key} to 4H: {len(ohlc)} candles")
        return resampled

async def main():
    mgr = ExternalFeedManager()
    mgr.fetch_all()
    resampled = mgr.resample_all_to_4h()
    for k, df in resampled.items():
        print(k, df.tail(3).to_dict("records"))

if __name__ == "__main__":
    asyncio.run(main())
