import numpy as np
import pandas as pd
from scipy.stats import entropy
from statsmodels.tsa.stattools import acf
from typing import Dict
from loguru import logger

class MarketEfficiencyAnalyzer:
    def __init__(self):
        pass

    def _sample_entropy(self, signal: np.ndarray, m: int = 2, r: float = None) -> float:
        N = len(signal)
        if r is None:
            r = 0.2 * np.std(signal)
        def _count_matches(template):
            dists = np.abs(signal[m:N-m] - template)
            return np.sum(dists < r)
        A = 0
        B = 0
        for i in range(N - m):
            template = signal[i]
            B += _count_matches(template)
        for i in range(N - m - 1):
            template = signal[i]
            A += _count_matches(template)
        if B == 0:
            return float('inf')
        return -np.log(A / B)

    def _variance_ratio(self, returns: np.ndarray, lag: int = 2) -> tuple:
        n = len(returns)
        if n < lag * 2:
            return 1.0, 1.0
        mu = np.mean(returns)
        var1 = np.var(returns, ddof=1)
        cum_returns = np.cumsum(returns)
        lagged = cum_returns[lag::lag] - cum_returns[:-lag:lag]
        var_k = np.var(lagged, ddof=1) / lag
        vr = var_k / var1 if var1 > 0 else 1.0
        se = np.sqrt((2 * (2 * lag - 1) * (lag - 1)) / (3 * lag * n))
        z = (vr - 1) / se if se > 0 else 0.0
        p_value = 2 * (1 - min(0.5, abs(z) / 10))  # rough approximation
        return vr, p_value

    def analyze(self, df: pd.DataFrame) -> Dict:
        returns = np.log(df["close"] / df["close"].shift(1)).dropna().values
        if len(returns) < 100:
            logger.warning(f"Efficiency needs >=100 returns, got {len(returns)}")
            return {}
        bins = np.percentile(returns, np.linspace(0, 100, 11))
        digitized = np.digitize(returns, bins)
        hist, _ = np.histogram(digitized, bins=np.arange(1, 13))
        shannon = entropy(hist + 1e-9)
        try:
            sampen = self._sample_entropy(returns[-500:], m=2)
        except Exception:
            sampen = 2.0
        vr2, p2 = self._variance_ratio(returns, lag=2)
        rw_rejected = p2 < 0.05
        efficiency_score = float(np.mean([shannon / np.log(len(hist)), min(1.0, sampen / 2.0), 1.0 - abs(vr2 - 1)]))
        predictability = "LOW" if efficiency_score > 0.7 else "MODERATE" if efficiency_score > 0.4 else "HIGH"
        return {
            "shannon_entropy": round(float(shannon), 4),
            "sample_entropy": round(float(sampen), 4),
            "variance_ratio_2": round(float(vr2), 4),
            "variance_ratio_p_value": round(float(p2), 4),
            "random_walk_rejected": bool(rw_rejected),
            "efficiency_score": round(float(efficiency_score), 4),
            "predictability_level": predictability
        }
