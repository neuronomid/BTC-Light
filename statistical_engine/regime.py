import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler
from typing import Dict, Optional
from loguru import logger

STATE_LABELS = ["BULL_TREND", "BEAR_TREND", "HIGH_VOL_RANGE", "LOW_VOL_RANGE"]

class RegimeClassifier:
    def __init__(self, n_states: int = 4, training_window: int = 1000):
        self.n_states = n_states
        self.training_window = training_window
        self.model: Optional[GaussianHMM] = None
        self.scaler = StandardScaler()

    def _build_features(self, df: pd.DataFrame) -> np.ndarray:
        returns = np.log(df["close"] / df["close"].shift(1)).dropna()
        rv = returns.rolling(window=20).std().dropna()
        volume_z = ((df["volume"] - df["volume"].rolling(20).mean()) /
                    df["volume"].rolling(20).std()).dropna()
        price_vs_ma = ((df["close"] - df["close"].rolling(20).mean()) /
                       df["close"].rolling(20).std()).dropna()
        feat_df = pd.concat([returns, rv, volume_z, price_vs_ma], axis=1).dropna()
        feat_df.columns = ["log_return", "realized_vol", "volume_z", "price_vs_ma"]
        return feat_df.values

    def fit(self, df: pd.DataFrame):
        data = self._build_features(df)
        if len(data) < self.training_window:
            logger.warning(f"Insufficient data: {len(data)} < {self.training_window}")
            return
        train = data[-self.training_window:]
        scaled = self.scaler.fit_transform(train)
        self.model = GaussianHMM(
            n_components=self.n_states,
            covariance_type="full",
            n_iter=100,
            random_state=42
        )
        self.model.fit(scaled)
        logger.info(f"HMM fitted: log-likelihood={self.model.monitor_.history[-1]:.2f}")

    def predict(self, df: pd.DataFrame) -> Dict:
        if self.model is None:
            raise RuntimeError("Model not fitted.")
        data = self._build_features(df)
        scaled = self.scaler.transform(data)
        state_probs = self.model.predict_proba(scaled)[-1]
        current_state_idx = int(np.argmax(state_probs))
        transition_matrix = self.model.transmat_

        expected_durations = []
        for i in range(self.n_states):
            p = transition_matrix[i, i]
            expected_durations.append(1.0 / (1.0 - p + 1e-9))

        transition_probs = {}
        for i in range(self.n_states):
            for j in range(self.n_states):
                transition_probs[f"{STATE_LABELS[i]}_to_{STATE_LABELS[j]}"] = round(transition_matrix[i, j], 4)

        return {
            "current_state": STATE_LABELS[current_state_idx],
            "state_probabilities": {
                STATE_LABELS[i]: round(float(state_probs[i]), 4)
                for i in range(self.n_states)
            },
            "expected_duration_candles": round(float(expected_durations[current_state_idx]), 2),
            "transition_probabilities": transition_probs,
            "state_confidence": round(float(state_probs[current_state_idx]), 4)
        }
