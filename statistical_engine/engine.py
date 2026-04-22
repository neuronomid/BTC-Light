import asyncio
import pandas as pd
from typing import Dict, Optional
from shared.redis_client import redis_client
from shared.db import AsyncSessionLocal, StatisticalSnapshot
from shared.time_utils import utc_now, utc_now_naive
from data.ingest_yahoo import YahooFinanceIngestor
from data.external_feeds import ExternalFeedManager
from statistical_engine.regime import RegimeClassifier
from statistical_engine.trend import TrendStrengthAnalyzer
from statistical_engine.volatility import VolatilityForecaster
from statistical_engine.change_point import ChangePointDetector
from statistical_engine.tail_risk import TailRiskAnalyzer
from statistical_engine.probability import ProbabilityEngine
from statistical_engine.efficiency import MarketEfficiencyAnalyzer
from statistical_engine.correlation import CorrelationAnalyzer
from config.settings import SYMBOL, TIMEFRAME
from loguru import logger

class StatisticalEngine:
    def __init__(self):
        self.ingestor = YahooFinanceIngestor()
        self.external = ExternalFeedManager()
        self.regime = RegimeClassifier()
        self.trend = TrendStrengthAnalyzer()
        self.vol = VolatilityForecaster()
        self.cp = ChangePointDetector()
        self.tail = TailRiskAnalyzer()
        self.prob = ProbabilityEngine()
        self.eff = MarketEfficiencyAnalyzer()
        self.corr = CorrelationAnalyzer()
        self._df: Optional[pd.DataFrame] = None
        self._external_df: Optional[Dict[str, pd.DataFrame]] = None

    async def refresh_data(self, fetch_external: bool = False) -> pd.DataFrame:
        self._df = await self.ingestor.run_once()
        if fetch_external:
            self.external.fetch_all()
            self._external_df = self.external.resample_all_to_4h()
        return self._df

    def run_all(self) -> Dict:
        if self._df is None or self._df.empty:
            raise RuntimeError("No data loaded. Call refresh_data() first.")
        df = self._df.copy()
        self.regime.fit(df)
        self.vol.fit(df)
        regime_data = self.regime.predict(df)
        trend_data = self.trend.analyze(df)
        vol_data = self.vol.forecast(df)
        cp_data = self.cp.detect(df)
        tail_data = self.tail.analyze(df)
        eff_data = self.eff.analyze(df)
        corr_data = self.corr.analyze(df, external=self._external_df)
        snapshot = {
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "timestamp": utc_now().isoformat(),
            "latest_close": float(df["close"].iloc[-1]) if not df.empty else None,
            "regime": regime_data,
            "trend": trend_data,
            "volatility": vol_data,
            "change_point": cp_data,
            "tail_risk": tail_data,
            "efficiency": eff_data,
            "correlation": corr_data,
        }
        return snapshot

    def evaluate_trade(self, direction: str, sl_pct: float, tp_pct: float) -> Dict:
        if self._df is None:
            raise RuntimeError("No data loaded.")
        garch_vol = self.vol.forecast(self._df).get("garch_forecast_4h")
        regime = self.regime.predict(self._df)
        # crude regime drift estimate
        drift_map = {"BULL_TREND": 0.001, "BEAR_TREND": -0.001, "HIGH_VOL_RANGE": 0.0, "LOW_VOL_RANGE": 0.0}
        drift = drift_map.get(regime.get("current_state"), 0.0)
        return self.prob.evaluate_trade(self._df, direction, sl_pct, tp_pct, garch_vol=garch_vol, regime_drift=drift)

    async def store_snapshot(self, snapshot: Dict):
        async with AsyncSessionLocal() as session:
            rec = StatisticalSnapshot(
                symbol=snapshot["symbol"],
                timestamp=utc_now_naive(),
                regime_data=snapshot.get("regime"),
                trend_data=snapshot.get("trend"),
                volatility_data=snapshot.get("volatility"),
                change_point_data=snapshot.get("change_point"),
                tail_risk_data=snapshot.get("tail_risk"),
                probability_data=None,
                efficiency_data=snapshot.get("efficiency"),
                correlation_data=snapshot.get("correlation"),
            )
            session.add(rec)
            await session.commit()
        logger.info("Statistical snapshot stored.")

    async def publish(self, snapshot: Dict):
        redis_client.publish("statistical:snapshot", snapshot)
        redis_client.set_json("latest_statistical_snapshot", snapshot, ttl=3600)
        logger.info("Statistical snapshot published to Redis.")

    async def run_cycle(self, fetch_external: bool = False):
        await self.refresh_data(fetch_external=fetch_external)
        snapshot = self.run_all()
        await self.store_snapshot(snapshot)
        await self.publish(snapshot)
        return snapshot

async def main():
    engine = StatisticalEngine()
    snapshot = await engine.run_cycle()
    print(snapshot)

if __name__ == "__main__":
    asyncio.run(main())
