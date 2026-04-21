import numpy as np
import pandas as pd
from typing import Dict
from loguru import logger

class ChangePointDetector:
    def __init__(self, hazard_rate: float = 1/200.0, cusum_threshold_percentile: float = 0.95):
        self.hazard_rate = hazard_rate
        self.cusum_threshold_percentile = cusum_threshold_percentile
        self.cusum_threshold = None
        self._returns_history = []

    def _bocpd(self, returns: np.ndarray) -> float:
        if len(returns) < 10:
            return 0.0
        n = len(returns)
        R = np.zeros((n + 1, n + 1))
        R[0, 0] = 1.0
        mu = np.mean(returns)
        sigma = max(np.std(returns), 1e-6)
        for t in range(1, n):
            predprobs = np.exp(-0.5 * ((returns[t - 1] - mu) / sigma) ** 2) / (sigma * np.sqrt(2 * np.pi))
            R[t, 1:t + 1] = R[t - 1, 0:t] * predprobs * (1 - self.hazard_rate)
            R[t, 0] = np.sum(R[t - 1, 0:t] * predprobs * self.hazard_rate)
            Z = np.sum(R[t, 0:t + 1])
            if Z > 0:
                R[t, 0:t + 1] /= Z
        cp_prob = float(R[-1, 0]) if n > 0 else 0.0
        return cp_prob

    def _cusum(self, returns: np.ndarray) -> bool:
        if len(returns) < 30:
            return False
        mu = np.mean(returns)
        sigma = max(np.std(returns), 1e-6)
        S_pos = 0.0
        S_neg = 0.0
        k = 0.5 * sigma
        for r in returns[-100:]:
            S_pos = max(0, S_pos + r - mu - k)
            S_neg = min(0, S_neg + r - mu + k)
        if self.cusum_threshold is None:
            self.cusum_threshold = np.percentile(np.abs(returns), self.cusum_threshold_percentile * 100)
        breached = abs(S_pos) > self.cusum_threshold or abs(S_neg) > self.cusum_threshold
        return breached

    def detect(self, df: pd.DataFrame) -> Dict:
        returns = np.log(df["close"] / df["close"].shift(1)).dropna().values
        if len(returns) < 50:
            logger.warning(f"Change point needs >=50 returns, got {len(returns)}")
            return {}
        bocpd_prob = self._bocpd(returns)
        cusum_breached = self._cusum(returns)
        last_cp = int(np.argmin(returns[-100:])) if len(returns) >= 100 else len(returns) // 2
        regime_stability = max(0.0, 1.0 - bocpd_prob)
        recommend_halt = bocpd_prob > 0.3 or cusum_breached
        return {
            "bocpd_change_probability": round(float(bocpd_prob), 4),
            "last_change_point_candles_ago": last_cp,
            "cusum_breached": bool(cusum_breached),
            "regime_stability_score": round(float(regime_stability), 4),
            "recommend_halt": bool(recommend_halt)
        }
