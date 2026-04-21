import numpy as np
import pandas as pd
from scipy.stats import genpareto
from typing import Dict
from loguru import logger

class TailRiskAnalyzer:
    def __init__(self, threshold_quantile: float = 0.95, window: int = 500):
        self.threshold_quantile = threshold_quantile
        self.window = window

    def _fit_gpd(self, losses: np.ndarray) -> tuple:
        threshold = np.percentile(losses, self.threshold_quantile * 100)
        exceedances = losses[losses > threshold] - threshold
        if len(exceedances) < 10:
            c, loc, scale = 0.1, 0, np.std(losses)
        else:
            c, loc, scale = genpareto.fit(exceedances, floc=0)
        return c, scale, threshold

    def _var_cvar(self, losses: np.ndarray, c: float, scale: float, threshold: float, alpha: float) -> tuple:
        if abs(c) < 1e-6:
            var = threshold + scale * np.log((1 - alpha) / (1 - self.threshold_quantile))
        else:
            var = threshold + (scale / c) * (((1 - alpha) / (1 - self.threshold_quantile)) ** (-c) - 1)
        if c < 1:
            cvar = var / (1 - c) + (scale - c * threshold) / (1 - c)
        else:
            cvar = var + scale / (1 + c)
        return var, cvar

    def analyze(self, df: pd.DataFrame) -> Dict:
        returns = np.log(df["close"] / df["close"].shift(1)).dropna().values
        if len(returns) < self.window:
            logger.warning(f"Tail risk needs >= {self.window} returns, got {len(returns)}")
            return {}
        losses = -returns[-self.window:]
        c, scale, threshold = self._fit_gpd(losses)
        var95, cvar95 = self._var_cvar(losses, c, scale, threshold, 0.95)
        var99, cvar99 = self._var_cvar(losses, c, scale, threshold, 0.99)
        tail_level = "ELEVATED" if cvar99 > 0.08 else "MODERATE" if cvar95 > 0.03 else "LOW"
        jumps = int(np.sum(np.abs(returns[-self.window:]) > 3 * np.std(returns[-self.window:])))
        return {
            "var_95_4h": round(float(var95), 4),
            "cvar_95_4h": round(float(cvar95), 4),
            "var_99_4h": round(float(var99), 4),
            "cvar_99_4h": round(float(cvar99), 4),
            "tail_index": round(float(c), 4),
            "tail_risk_level": tail_level,
            "recent_jumps_detected": jumps
        }
