import math
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from statistical_engine.change_point import ChangePointDetector
from statistical_engine.correlation import CorrelationAnalyzer
from statistical_engine.efficiency import MarketEfficiencyAnalyzer
from statistical_engine.probability import ProbabilityEngine
from statistical_engine.regime import RegimeClassifier
from statistical_engine.tail_risk import TailRiskAnalyzer
from statistical_engine.trend import TrendStrengthAnalyzer
from statistical_engine.volatility import VolatilityForecaster


def make_ohlcv(n=600, start=100.0, drift=0.0007, shock_at=None, shock_size=0.0):
    rng = np.random.default_rng(42)
    noise = rng.normal(0.0, 0.006, n)
    seasonal = 0.002 * np.sin(np.arange(n) / 17.0)
    returns = drift + seasonal + noise
    if shock_at is not None:
        returns[shock_at:] += shock_size
    close = start * np.exp(np.cumsum(returns))
    open_ = np.r_[start, close[:-1]]
    spread = np.maximum(close * 0.003, 0.01)
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    volume = 1000 + 50 * np.sin(np.arange(n) / 9.0) + rng.normal(0, 10, n)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.maximum(volume, 1.0),
        }
    )


def frame_from_returns(returns, start=100.0):
    close = start * np.exp(np.cumsum(returns))
    open_ = np.r_[start, close[:-1]]
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=len(close), freq="4h", tz="UTC"),
            "open": open_,
            "high": np.maximum(open_, close) * 1.002,
            "low": np.minimum(open_, close) * 0.998,
            "close": close,
            "volume": np.full(len(close), 1000.0),
        }
    )


class TestRegimeClassifier(unittest.TestCase):
    def test_build_features_returns_finite_four_column_matrix(self):
        df = make_ohlcv(120)
        features = RegimeClassifier(training_window=20)._build_features(df)

        self.assertEqual(features.shape[1], 4)
        self.assertGreater(len(features), 80)
        self.assertTrue(np.isfinite(features).all())

    def test_fit_leaves_model_unset_when_training_window_is_not_met(self):
        classifier = RegimeClassifier(training_window=500)

        classifier.fit(make_ohlcv(80))

        self.assertIsNone(classifier.model)

    def test_predict_maps_highest_probability_state_and_transition_matrix(self):
        df = make_ohlcv(160)
        classifier = RegimeClassifier(training_window=20)
        features = classifier._build_features(df)
        classifier.scaler.fit(features)

        class FakeModel:
            transmat_ = np.array(
                [
                    [0.80, 0.10, 0.05, 0.05],
                    [0.20, 0.60, 0.10, 0.10],
                    [0.10, 0.10, 0.70, 0.10],
                    [0.15, 0.10, 0.15, 0.60],
                ]
            )

            def predict_proba(self, values):
                probs = np.tile(np.array([0.1, 0.7, 0.1, 0.1]), (len(values), 1))
                return probs

        classifier.model = FakeModel()

        result = classifier.predict(df)

        self.assertEqual(result["current_state"], "BEAR_TREND")
        self.assertEqual(result["state_confidence"], 0.7)
        self.assertAlmostEqual(sum(result["state_probabilities"].values()), 1.0)
        self.assertEqual(len(result["transition_probabilities"]), 16)
        self.assertGreater(result["expected_duration_candles"], 0)


class TestTrendVolatilityAndRiskAnalyzers(unittest.TestCase):
    def test_trend_analyzer_returns_empty_for_insufficient_history(self):
        self.assertEqual(TrendStrengthAnalyzer().analyze(make_ohlcv(100)), {})

    def test_trend_analyzer_returns_bounded_metrics_for_long_history(self):
        result = TrendStrengthAnalyzer().analyze(make_ohlcv(620))

        self.assertIn(result["trend_classification"], {"TRENDING", "MEAN_REVERTING", "RANDOM_WALK"})
        self.assertGreaterEqual(result["hurst_100"], 0.0)
        self.assertLessEqual(result["hurst_100"], 1.0)
        self.assertGreaterEqual(result["hurst_500"], 0.0)
        self.assertLessEqual(result["hurst_500"], 1.0)
        self.assertGreaterEqual(result["trend_strength_score"], 0.0)
        self.assertLessEqual(result["trend_strength_score"], 1.0)
        self.assertIsInstance(result["is_stationary"], bool)

    def test_volatility_forecast_returns_empty_for_short_history(self):
        self.assertEqual(VolatilityForecaster().forecast(make_ohlcv(20)), {})

    def test_volatility_fit_uses_garch_models_and_forecast_shapes_output(self):
        df = make_ohlcv(160)

        class FakeForecast:
            def __init__(self, variance):
                self.variance = pd.DataFrame([[variance]])

        class FakeResult:
            def __init__(self, variance):
                self._variance = variance

            def forecast(self, horizon):
                self.horizon = horizon
                return FakeForecast(self._variance)

        class FakeArchModel:
            def __init__(self, variance):
                self.variance = variance

            def fit(self, disp):
                self.disp = disp
                return FakeResult(self.variance)

        created_vols = []

        def fake_arch_model(returns, vol, p, q, rescale):
            created_vols.append(vol)
            return FakeArchModel(4.0 if vol == "Garch" else 9.0)

        forecaster = VolatilityForecaster()
        with patch("statistical_engine.volatility.arch_model", side_effect=fake_arch_model):
            forecaster.fit(df)

        result = forecaster.forecast(df)

        self.assertEqual(created_vols, ["Garch", "EGARCH"])
        self.assertEqual(result["garch_forecast_4h"], 0.02)
        self.assertEqual(result["egarch_forecast_4h"], 0.03)
        self.assertIn(result["vol_regime"], {"LOW", "NORMAL", "HIGH"})
        self.assertTrue(result["leverage_effect_active"])

    def test_change_point_detector_returns_empty_for_short_history(self):
        self.assertEqual(ChangePointDetector().detect(make_ohlcv(20)), {})

    def test_change_point_detector_returns_stability_and_halt_flags(self):
        result = ChangePointDetector().detect(make_ohlcv(180))

        self.assertGreaterEqual(result["bocpd_change_probability"], 0.0)
        self.assertLessEqual(result["bocpd_change_probability"], 1.0)
        self.assertGreaterEqual(result["regime_stability_score"], 0.0)
        self.assertLessEqual(result["regime_stability_score"], 1.0)
        self.assertIsInstance(result["cusum_breached"], bool)
        self.assertIsInstance(result["recommend_halt"], bool)

    def test_tail_risk_returns_empty_for_short_history(self):
        self.assertEqual(TailRiskAnalyzer(window=100).analyze(make_ohlcv(50)), {})

    def test_tail_risk_reports_var_cvar_and_jump_counts(self):
        result = TailRiskAnalyzer(window=300).analyze(make_ohlcv(420))

        self.assertIn(result["tail_risk_level"], {"LOW", "MODERATE", "ELEVATED"})
        self.assertGreaterEqual(result["recent_jumps_detected"], 0)
        self.assertTrue(math.isfinite(result["var_95_4h"]))
        self.assertTrue(math.isfinite(result["cvar_95_4h"]))
        self.assertTrue(math.isfinite(result["var_99_4h"]))
        self.assertTrue(math.isfinite(result["cvar_99_4h"]))


class TestProbabilityEfficiencyAndCorrelation(unittest.TestCase):
    def test_probability_returns_empty_for_insufficient_history(self):
        self.assertEqual(ProbabilityEngine(n_paths=8).evaluate_trade(make_ohlcv(50), "LONG", 0.02, 0.04), {})

    def test_probability_long_trade_is_deterministic_with_zero_vol_upward_drift(self):
        result = ProbabilityEngine(n_paths=64).evaluate_trade(
            make_ohlcv(140),
            direction="LONG",
            stop_loss_pct=0.02,
            take_profit_pct=0.04,
            garch_vol=0.0,
            regime_drift=0.02,
        )

        self.assertEqual(result["prob_hit_tp_before_sl"], 1.0)
        self.assertEqual(result["expected_value_per_trade"], 0.04)
        self.assertEqual(result["bayesian_posterior_long"], 1.0)
        self.assertEqual(result["kelly_fraction"], 1.0)
        self.assertEqual(result["recommended_size_pct_equity"], 0.02)

    def test_probability_short_trade_is_deterministic_with_zero_vol_downward_drift(self):
        result = ProbabilityEngine(n_paths=64).evaluate_trade(
            make_ohlcv(140),
            direction="SHORT",
            stop_loss_pct=0.02,
            take_profit_pct=0.04,
            garch_vol=0.0,
            regime_drift=-0.02,
        )

        self.assertEqual(result["prob_hit_tp_before_sl"], 1.0)
        self.assertEqual(result["expected_value_per_trade"], 0.04)
        self.assertEqual(result["bayesian_posterior_short"], 1.0)

    def test_efficiency_returns_empty_for_short_history(self):
        self.assertEqual(MarketEfficiencyAnalyzer().analyze(make_ohlcv(60)), {})

    def test_efficiency_reports_random_walk_diagnostics(self):
        result = MarketEfficiencyAnalyzer().analyze(make_ohlcv(180))

        self.assertIn(result["predictability_level"], {"LOW", "MODERATE", "HIGH"})
        self.assertGreaterEqual(result["efficiency_score"], 0.0)
        self.assertLessEqual(result["efficiency_score"], 1.0)
        self.assertIsInstance(result["random_walk_rejected"], bool)

    def test_correlation_returns_default_shape_without_external_feeds(self):
        result = CorrelationAnalyzer().analyze(make_ohlcv(80))

        self.assertEqual(result["risk_on_off_regime"], "MIXED")
        self.assertIsNone(result["corr_btc_spx_30d"])
        self.assertIsNone(result["tail_dependence_btc_spx"])

    def test_correlation_uses_external_feeds_for_risk_on_regime(self):
        base_returns = np.linspace(-0.01, 0.01, 80)
        btc = frame_from_returns(base_returns, start=100.0)
        external = {
            "btc_spx": frame_from_returns(base_returns * 1.1, start=3000.0),
            "btc_dxy": frame_from_returns(base_returns * -0.8, start=100.0),
            "btc_gold": frame_from_returns(base_returns * 0.2, start=1900.0),
            "btc_eth": frame_from_returns(base_returns * 0.9, start=1500.0),
        }

        result = CorrelationAnalyzer().analyze(btc, external=external)

        self.assertGreater(result["corr_btc_spx_30d"], 0.99)
        self.assertLess(result["corr_btc_dxy_30d"], -0.99)
        self.assertEqual(result["risk_on_off_regime"], "RISK_ON")


if __name__ == "__main__":
    unittest.main()
