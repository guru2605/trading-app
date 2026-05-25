"""XGBoost adaptive weights — learns indicator importance from signal outcomes.

Requires outcome data from signal tracking (Task 2.1). Trains monthly on a
rolling 6-month window. Features = indicator values from signal JSON,
target = win/loss outcome.

Optional deps: xgboost, scikit-learn. Falls back to static weights if unavailable.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.signal import Signal

logger = logging.getLogger(__name__)

_ML_AVAILABLE = False
try:
    import numpy as np
    from sklearn.model_selection import train_test_split
    from xgboost import XGBClassifier

    _ML_AVAILABLE = True
except ImportError:
    pass

# Features extracted from signal indicators JSON
FEATURE_KEYS: list[str] = [
    "rsi.value",
    "macd.histogram_positive",
    "ema.bullish_crossover",
    "ema.bearish_crossover",
    "vwap.price_above_vwap",
    "bollinger.near_lower",
    "bollinger.near_upper",
    "volume.spike",
    "volume.ratio",
    "atr.pct",
    "adx.value",
    "stoch_rsi.value",
    "supertrend.bullish",
    "supertrend.buy_signal",
    "obv.bullish_divergence",
    "obv.bearish_divergence",
    "cmf.value",
    "support_resistance.near_support",
    "support_resistance.near_resistance",
    "week_52.near_high",
    "week_52.near_low",
]


class MLWeightsService:
    """Trains XGBoost on historical signal outcomes to learn indicator importance."""

    def __init__(self) -> None:
        self._model: Any = None
        self._feature_importance: dict[str, float] = {}
        self._last_trained: datetime | None = None
        self._min_samples: int = 50

    @property
    def available(self) -> bool:
        return _ML_AVAILABLE and self._model is not None

    @property
    def feature_importance(self) -> dict[str, float]:
        return dict(self._feature_importance)

    async def train(self, db: AsyncSession, lookback_months: int = 6) -> dict[str, Any]:
        """Train XGBoost on resolved signals from the last N months.

        Returns training summary with accuracy, feature importance, sample count.
        """
        if not _ML_AVAILABLE:
            return {"available": False, "reason": "xgboost/scikit-learn not installed"}

        cutoff = datetime.now(UTC) - timedelta(days=lookback_months * 30)
        result = await db.execute(
            select(Signal).where(
                Signal.outcome.in_(["win", "loss"]),
                Signal.created_at >= cutoff,
            )
        )
        signals = list(result.scalars().all())

        if len(signals) < self._min_samples:
            return {
                "available": False,
                "reason": f"Need at least {self._min_samples} resolved signals, have {len(signals)}",
                "signal_count": len(signals),
            }

        features, targets = self._prepare_dataset(signals)
        if len(features) < self._min_samples:
            return {"available": False, "reason": "Insufficient valid features", "signal_count": len(signals)}

        feat_train, feat_test, y_train, y_test = train_test_split(
            features, targets, test_size=0.2, random_state=42, stratify=targets
        )

        model = XGBClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.1,
            eval_metric="logloss",
            random_state=42,
        )
        model.fit(feat_train, y_train)

        accuracy = float(model.score(feat_test, y_test))
        importances = model.feature_importances_

        self._feature_importance = {}
        for i, key in enumerate(FEATURE_KEYS):
            if i < len(importances):
                self._feature_importance[key] = round(float(importances[i]), 4)

        self._model = model
        self._last_trained = datetime.now(UTC)

        # Sort by importance
        sorted_features = sorted(self._feature_importance.items(), key=lambda x: x[1], reverse=True)

        return {
            "available": True,
            "accuracy": round(accuracy, 4),
            "sample_count": len(features),
            "train_size": len(feat_train),
            "test_size": len(feat_test),
            "top_features": sorted_features[:10],
            "trained_at": self._last_trained.isoformat(),
        }

    def predict_outcome(self, indicators: dict[str, Any]) -> dict[str, Any]:
        """Predict win probability for a signal given its indicators."""
        if not self.available:
            return {"available": False}

        features = self._extract_features(indicators)
        feature_array = np.array([features])
        proba = self._model.predict_proba(feature_array)[0]

        # proba[0] = loss probability, proba[1] = win probability
        win_prob = float(proba[1]) if len(proba) > 1 else 0.5

        return {
            "available": True,
            "win_probability": round(win_prob, 4),
            "confidence_modifier": self._prob_to_modifier(win_prob),
        }

    def get_weight_adjustments(self) -> dict[str, float]:
        """Get scoring weight adjustments based on learned feature importance.

        Returns multipliers (0.5 to 2.0) for each indicator category.
        Higher importance → higher multiplier.
        """
        if not self._feature_importance:
            return {}

        values = list(self._feature_importance.values())
        if not values:
            return {}

        mean_imp = sum(values) / len(values)
        if mean_imp == 0:
            return {}

        adjustments: dict[str, float] = {}
        for key, importance in self._feature_importance.items():
            category = key.split(".")[0]  # e.g., "rsi.value" → "rsi"
            ratio = importance / mean_imp
            modifier = max(0.5, min(2.0, ratio))
            if category not in adjustments:
                adjustments[category] = round(modifier, 2)
            else:
                # Average multiple features from same category
                adjustments[category] = round((adjustments[category] + modifier) / 2, 2)

        return adjustments

    def _prepare_dataset(self, signals: list[Signal]) -> tuple[Any, Any]:
        """Extract feature matrix X and target vector y from signals."""
        feature_rows: list[list[float]] = []
        y_list: list[int] = []

        for signal in signals:
            indicators = signal.indicators or {}
            features = self._extract_features(indicators)
            if any(f != 0.0 for f in features):  # Skip all-zero rows
                feature_rows.append(features)
                y_list.append(1 if signal.outcome == "win" else 0)

        return np.array(feature_rows), np.array(y_list)

    @staticmethod
    def _extract_features(indicators: dict[str, Any]) -> list[float]:
        """Extract feature vector from indicators dict."""
        features: list[float] = []
        for key in FEATURE_KEYS:
            parts = key.split(".")
            value: Any = indicators
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part, 0)
                else:
                    value = 0
                    break
            if isinstance(value, bool):
                features.append(1.0 if value else 0.0)
            elif isinstance(value, int | float):
                features.append(float(value))
            else:
                features.append(0.0)
        return features

    @staticmethod
    def _prob_to_modifier(win_prob: float) -> float:
        """Convert win probability to confidence modifier (0.8 to 1.2)."""
        if win_prob >= 0.7:
            return 1.15
        elif win_prob >= 0.6:
            return 1.05
        elif win_prob <= 0.3:
            return 0.85
        elif win_prob <= 0.4:
            return 0.92
        return 1.0
