"""Tests for MLWeightsService."""

from typing import Any

from app.services.ml_weights import FEATURE_KEYS, MLWeightsService


class TestMLWeightsService:
    def test_extract_features_empty(self) -> None:
        features = MLWeightsService._extract_features({})
        assert len(features) == len(FEATURE_KEYS)
        assert all(f == 0.0 for f in features)

    def test_extract_features_with_data(self) -> None:
        indicators: dict[str, Any] = {
            "rsi": {"value": 45.0},
            "macd": {"histogram_positive": True},
            "ema": {"bullish_crossover": False, "bearish_crossover": False},
            "supertrend": {"bullish": True, "buy_signal": False},
        }
        features = MLWeightsService._extract_features(indicators)
        assert len(features) == len(FEATURE_KEYS)
        # rsi.value = 45.0
        assert features[0] == 45.0
        # macd.histogram_positive = True → 1.0
        assert features[1] == 1.0

    def test_extract_features_bool_to_float(self) -> None:
        indicators: dict[str, Any] = {"volume": {"spike": True, "ratio": 2.5}}
        features = MLWeightsService._extract_features(indicators)
        # volume.spike index
        spike_idx = FEATURE_KEYS.index("volume.spike")
        assert features[spike_idx] == 1.0
        ratio_idx = FEATURE_KEYS.index("volume.ratio")
        assert features[ratio_idx] == 2.5

    def test_prob_to_modifier_high(self) -> None:
        assert MLWeightsService._prob_to_modifier(0.8) == 1.15

    def test_prob_to_modifier_medium(self) -> None:
        assert MLWeightsService._prob_to_modifier(0.65) == 1.05

    def test_prob_to_modifier_low(self) -> None:
        assert MLWeightsService._prob_to_modifier(0.25) == 0.85

    def test_prob_to_modifier_neutral(self) -> None:
        assert MLWeightsService._prob_to_modifier(0.5) == 1.0

    def test_not_available_without_training(self) -> None:
        service = MLWeightsService()
        assert service.available is False
        assert service.feature_importance == {}

    def test_predict_without_model(self) -> None:
        service = MLWeightsService()
        result = service.predict_outcome({"rsi": {"value": 50}})
        assert result == {"available": False}

    def test_get_weight_adjustments_empty(self) -> None:
        service = MLWeightsService()
        assert service.get_weight_adjustments() == {}

    def test_get_weight_adjustments_with_importance(self) -> None:
        service = MLWeightsService()
        service._feature_importance = {
            "rsi.value": 0.2,
            "macd.histogram_positive": 0.1,
            "ema.bullish_crossover": 0.05,
        }
        adjustments = service.get_weight_adjustments()
        assert "rsi" in adjustments
        assert "macd" in adjustments
        assert "ema" in adjustments
        # rsi has highest importance → should get highest modifier
        assert adjustments["rsi"] >= adjustments["ema"]
