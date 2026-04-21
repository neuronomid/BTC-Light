import numpy as np
import pandas as pd
import nolds
from statsmodels.tsa.stattools import adfuller
from typing import Dict
from loguru import logger

def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm[plus_dm < 0] = 0
    minus_dm[minus_dm < 0] = 0
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, min_periods=period).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr)
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9)) * 100
    adx = dx.ewm(alpha=1/period, min_periods=period).mean()
    return float(adx.iloc[-1]) if not adx.empty else 0.0

class TrendStrengthAnalyzer:
    def __init__(self):
        pass

    def analyze(self, df: pd.DataFrame) -> Dict:
        closes = df["close"].dropna().values
        if len(closes) < 500:
            logger.warning(f"Trend analysis needs >=500 points, got {len(closes)}")
            return {}

        try:
            hurst_100 = max(0.0, min(1.0, nolds.dfa(closes[-100:])))
        except Exception:
            hurst_100 = 0.5
        try:
            hurst_500 = max(0.0, min(1.0, nolds.dfa(closes[-500:])))
        except Exception:
            hurst_500 = 0.5

        adf_result = adfuller(closes[-500:], autolag="AIC")
        adf_stat, adf_pvalue = adf_result[0], adf_result[1]
        is_stationary = adf_pvalue < 0.05

        adx_val = _adx(df["high"], df["low"], df["close"], period=14)

        if hurst_100 > 0.55 and adx_val > 25:
            trend_classification = "TRENDING"
        elif hurst_100 < 0.45 and is_stationary:
            trend_classification = "MEAN_REVERTING"
        else:
            trend_classification = "RANDOM_WALK"

        trend_strength_score = min(1.0, max(0.0, (hurst_100 - 0.5) * 5 + adx_val / 50))

        return {
            "hurst_100": round(float(hurst_100), 4),
            "hurst_500": round(float(hurst_500), 4),
            "trend_classification": trend_classification,
            "adf_statistic": round(float(adf_stat), 4),
            "adf_p_value": round(float(adf_pvalue), 4),
            "is_stationary": bool(is_stationary),
            "adx": round(float(adx_val), 4),
            "trend_strength_score": round(float(trend_strength_score), 4)
        }
