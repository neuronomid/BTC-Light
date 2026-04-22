from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from config.settings import SYMBOL, TIMEFRAME
from statistical_engine.change_point import ChangePointDetector
from statistical_engine.correlation import CorrelationAnalyzer
from statistical_engine.efficiency import MarketEfficiencyAnalyzer
from statistical_engine.probability import ProbabilityEngine
from statistical_engine.regime import RegimeClassifier, STATE_LABELS
from statistical_engine.tail_risk import TailRiskAnalyzer
from statistical_engine.trend import TrendStrengthAnalyzer
from statistical_engine.volatility import VolatilityForecaster


class InsufficientHistory(Exception):
    pass


def derive_regime_state_labels(df: pd.DataFrame, training_window: int) -> Tuple[str, ...]:
    classifier = RegimeClassifier(training_window=training_window)
    classifier.fit(df)
    if classifier.model is None:
        return tuple(STATE_LABELS)

    features = classifier._build_features(df)
    if len(features) < training_window:
        return tuple(STATE_LABELS)
    train = features[-training_window:]
    scaled = classifier.scaler.transform(train)
    hidden = classifier.model.predict(scaled)

    state_stats = []
    for state in range(classifier.n_states):
        mask = hidden == state
        if not mask.any():
            state_stats.append((state, 0.0, 0.0))
            continue
        state_stats.append((state, float(train[mask, 0].mean()), float(train[mask, 1].mean())))

    labels = [None] * classifier.n_states
    bull = max(state_stats, key=lambda item: item[1])[0]
    bear = min(state_stats, key=lambda item: item[1])[0]
    labels[bull] = "BULL_TREND"
    labels[bear] = "BEAR_TREND"
    remaining = [item for item in state_stats if labels[item[0]] is None]
    if remaining:
        high_vol = max(remaining, key=lambda item: item[2])[0]
        labels[high_vol] = "HIGH_VOL_RANGE"
    for index, value in enumerate(labels):
        if value is None:
            labels[index] = "LOW_VOL_RANGE"
    return tuple(labels)


class HistoricalSnapshotBuilder:
    def __init__(self, profile):
        self.profile = profile
        self.regime = RegimeClassifier(training_window=profile.hmm_training_window)
        self.trend = TrendStrengthAnalyzer()
        self.vol = VolatilityForecaster()
        self.cp = ChangePointDetector()
        self.tail = TailRiskAnalyzer()
        self.eff = MarketEfficiencyAnalyzer()
        self.corr = CorrelationAnalyzer()
        self.prob = ProbabilityEngine(n_paths=profile.monte_carlo_paths)
        self._last_fit_index: Optional[int] = None
        self._last_df: Optional[pd.DataFrame] = None

    def _should_refit(self, end_index: int) -> bool:
        if self._last_fit_index is None:
            return True
        return end_index - self._last_fit_index >= self.profile.refit_interval_candles

    def _fit_models(self, df: pd.DataFrame, end_index: int):
        features = self.regime._build_features(df)
        if len(features) < self.profile.hmm_training_window:
            raise InsufficientHistory(f"HMM needs at least {self.profile.hmm_training_window} feature rows.")
        self.regime.fit(df)
        if self.regime.model is None:
            raise InsufficientHistory(f"HMM needs at least {self.profile.hmm_training_window} feature rows.")
        self.vol.fit(df)
        self._last_fit_index = end_index

    def _predict_regime(self, df: pd.DataFrame) -> Dict:
        if self.regime.model is None:
            raise InsufficientHistory("HMM model is not fitted.")
        data = self.regime._build_features(df)
        if len(data) == 0:
            raise InsufficientHistory("No HMM features available.")
        scaled = self.regime.scaler.transform(data)
        state_probs = self.regime.model.predict_proba(scaled)[-1]
        current_state_idx = int(np.argmax(state_probs))
        transition_matrix = self.regime.model.transmat_
        labels = list(self.profile.regime_state_labels)
        if len(labels) != self.regime.n_states:
            labels = list(STATE_LABELS)

        expected_durations = []
        for i in range(self.regime.n_states):
            p = transition_matrix[i, i]
            expected_durations.append(1.0 / (1.0 - p + 1e-9))

        transition_probs = {}
        for i in range(self.regime.n_states):
            for j in range(self.regime.n_states):
                transition_probs[f"{labels[i]}_to_{labels[j]}"] = round(float(transition_matrix[i, j]), 4)

        return {
            "current_state": labels[current_state_idx],
            "state_probabilities": {
                labels[i]: round(float(state_probs[i]), 4)
                for i in range(self.regime.n_states)
            },
            "expected_duration_candles": round(float(expected_durations[current_state_idx]), 2),
            "transition_probabilities": transition_probs,
            "state_confidence": round(float(state_probs[current_state_idx]), 4),
        }

    def build(self, df: pd.DataFrame, end_index: int, decision_time: pd.Timestamp) -> Dict:
        df_slice = df.iloc[: end_index + 1].copy()
        self._last_df = df_slice
        if self._should_refit(end_index):
            self._fit_models(df_slice, end_index)

        regime_data = self._predict_regime(df_slice)
        snapshot = {
            "symbol": SYMBOL,
            "timeframe": TIMEFRAME,
            "timestamp": decision_time.isoformat(),
            "latest_close": float(df_slice["close"].iloc[-1]),
            "regime": regime_data,
            "trend": self.trend.analyze(df_slice),
            "volatility": self.vol.forecast(df_slice),
            "change_point": self.cp.detect(df_slice),
            "tail_risk": self.tail.analyze(df_slice),
            "efficiency": self.eff.analyze(df_slice),
            "correlation": self.corr.analyze(df_slice, external=None),
        }
        return snapshot

    def evaluate_trade(self, snapshot: Dict, action: str, sl_pct: float, tp_pct: float, seed: int) -> Dict:
        if self._last_df is None:
            return {}
        garch_vol = snapshot.get("volatility", {}).get("garch_forecast_4h")
        state = snapshot.get("regime", {}).get("current_state")
        drift_map = {"BULL_TREND": 0.001, "BEAR_TREND": -0.001, "HIGH_VOL_RANGE": 0.0, "LOW_VOL_RANGE": 0.0}
        np.random.seed(seed)
        return self.prob.evaluate_trade(
            self._last_df,
            action,
            sl_pct,
            tp_pct,
            garch_vol=garch_vol,
            regime_drift=drift_map.get(state, 0.0),
        )
