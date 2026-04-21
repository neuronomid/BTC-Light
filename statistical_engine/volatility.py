import numpy as np
import pandas as pd
from arch import arch_model
from typing import Dict
from loguru import logger

class VolatilityForecaster:
    def __init__(self):
        self.garch_result = None
        self.egarch_result = None

    def _realized_vol(self, returns: pd.Series, window: int) -> float:
        if len(returns) < window:
            return float(returns.std() / 100.0)
        return float(returns.iloc[-window:].std() / 100.0)

    def fit(self, df: pd.DataFrame):
        returns = 100 * np.log(df["close"] / df["close"].shift(1)).dropna()
        if len(returns) < 100:
            logger.warning("Need >=100 returns for GARCH")
            return
        try:
            am_g = arch_model(returns, vol="Garch", p=1, q=1, rescale=False)
            self.garch_result = am_g.fit(disp="off")
        except Exception as e:
            logger.error(f"GARCH fit failed: {e}")
        try:
            am_e = arch_model(returns, vol="EGARCH", p=1, q=1, rescale=False)
            self.egarch_result = am_e.fit(disp="off")
        except Exception as e:
            logger.error(f"EGARCH fit failed: {e}")

    def forecast(self, df: pd.DataFrame) -> Dict:
        returns = 100 * np.log(df["close"] / df["close"].shift(1)).dropna()
        if len(returns) < 30:
            return {}

        garch_forecast = self.garch_result.forecast(horizon=1).variance.iloc[-1, 0] ** 0.5 / 100 if self.garch_result else returns.std() / 100
        egarch_forecast = self.egarch_result.forecast(horizon=1).variance.iloc[-1, 0] ** 0.5 / 100 if self.egarch_result else returns.std() / 100

        rv_1d = self._realized_vol(returns, 6)   # 6 * 4H ≈ 1D
        rv_7d = self._realized_vol(returns, 42)  # 42 * 4H ≈ 1W
        rv_30d = self._realized_vol(returns, 180) # 180 * 4H ≈ 1M

        vol_percentile = float(np.mean(returns.iloc[-90*6:].std() < returns.std())) if len(returns) >= 90*6 else 0.5

        if vol_percentile > 0.8:
            vol_regime = "HIGH"
        elif vol_percentile < 0.2:
            vol_regime = "LOW"
        else:
            vol_regime = "NORMAL"

        leverage = egarch_forecast > garch_forecast * 1.1 if garch_forecast else False

        return {
            "garch_forecast_4h": round(float(garch_forecast), 6),
            "egarch_forecast_4h": round(float(egarch_forecast), 6),
            "realized_vol_1d": round(float(rv_1d), 6),
            "realized_vol_7d": round(float(rv_7d), 6),
            "realized_vol_30d": round(float(rv_30d), 6),
            "vol_percentile_90d": round(float(vol_percentile), 4),
            "vol_regime": vol_regime,
            "leverage_effect_active": bool(leverage)
        }
