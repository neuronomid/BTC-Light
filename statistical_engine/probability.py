import numpy as np
import pandas as pd
from typing import Dict
from loguru import logger

class ProbabilityEngine:
    def __init__(self, n_paths: int = 10000):
        self.n_paths = n_paths

    def evaluate_trade(
        self,
        df: pd.DataFrame,
        direction: str,
        stop_loss_pct: float,
        take_profit_pct: float,
        garch_vol: float = None,
        regime_drift: float = 0.0
    ) -> Dict:
        closes = df["close"].values
        if len(closes) < 100:
            return {}
        returns = np.log(closes[1:] / closes[:-1])
        mu = float(np.mean(returns[-100:])) + regime_drift
        sigma = garch_vol if garch_vol is not None else float(np.std(returns[-100:]))
        T = 18  # max 18 * 4H ≈ 3 days
        S0 = float(closes[-1])
        dt = 1.0
        paths = np.zeros((self.n_paths, T))
        paths[:, 0] = S0
        for t in range(1, T):
            Z = np.random.standard_normal(self.n_paths)
            paths[:, t] = paths[:, t - 1] * np.exp((mu - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * Z)
        if direction.upper() == "LONG":
            sl = S0 * (1 - stop_loss_pct)
            tp = S0 * (1 + take_profit_pct)
            hit_sl = np.min(paths, axis=1) <= sl
            hit_tp = np.max(paths, axis=1) >= tp
        else:
            sl = S0 * (1 + stop_loss_pct)
            tp = S0 * (1 - take_profit_pct)
            hit_sl = np.max(paths, axis=1) >= sl
            hit_tp = np.min(paths, axis=1) <= tp
        sl_first = 0
        tp_first = 0
        for i in range(self.n_paths):
            for t in range(1, T):
                if hit_sl[i] and (not hit_tp[i] or (hit_tp[i] and np.argmax(paths[i] >= tp if direction.upper() == "LONG" else paths[i] <= tp) > np.argmax(paths[i] <= sl if direction.upper() == "LONG" else paths[i] >= sl))):
                    pass
            if hit_tp[i] and not hit_sl[i]:
                tp_first += 1
            elif hit_tp[i] and hit_sl[i]:
                tp_first += 1
            elif hit_sl[i]:
                sl_first += 1
        prob_tp = tp_first / self.n_paths
        prob_sl = sl_first / self.n_paths
        ev = prob_tp * take_profit_pct - prob_sl * stop_loss_pct
        b = take_profit_pct / max(stop_loss_pct, 1e-6)
        p = prob_tp
        q = 1 - p
        kelly = (p * b - q) / b if b > 0 else 0.0
        kelly = max(0.0, kelly)
        size = min(kelly * 0.25, 0.02)
        return {
            "prob_hit_tp_before_sl": round(float(prob_tp), 4),
            "expected_value_per_trade": round(float(ev), 6),
            "bayesian_posterior_long": round(float(p), 4) if direction.upper() == "LONG" else round(float(1 - p), 4),
            "bayesian_posterior_short": round(float(1 - p), 4) if direction.upper() == "LONG" else round(float(p), 4),
            "kelly_fraction": round(float(kelly), 4),
            "recommended_size_pct_equity": round(float(size), 6)
        }
