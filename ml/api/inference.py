from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from ml.src.config import MODEL_DIR, PROCESSED_DIR


DEFAULT_THRESH_LOW = 0.30
DEFAULT_THRESH_HIGH = 0.60
DEFAULT_THRESH_CRITICAL = 0.85


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_feature_input(raw: dict[str, Any]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for key, value in raw.items():
        if value is None:
            continue
        try:
            num = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(num):
            normalized[key] = num
    return normalized


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return default
    return num if np.isfinite(num) else default


@dataclass
class InferenceOutput:
    risk_score: float
    risk_level: str
    contributing_factors: list[dict[str, Any]]
    recommendations: list[str]
    predicted_at: str
    model_version: str


class XgbSepsisRuntime:
    def __init__(self) -> None:
        self.model_path = MODEL_DIR / "xgb_final_models.pkl"
        self.feature_path = PROCESSED_DIR / "xgb_selected_features.csv"
        self.threshold_path = PROCESSED_DIR / "risk_thresholds.csv"
        self.median_path = PROCESSED_DIR / "feature_medians.csv"
        self.feature_dataset_path = PROCESSED_DIR / "features_final.csv"

        self.models: list[Any] = []
        self.features: list[str] = []
        self.threshold_low = DEFAULT_THRESH_LOW
        self.threshold_high = DEFAULT_THRESH_HIGH
        self.threshold_critical = DEFAULT_THRESH_CRITICAL
        self.feature_medians: dict[str, float] = {}
        self.model_version = "xgb_final_models_v1"
        self._shap_explainer: Any | None = None

    def load(self) -> None:
        if not self.model_path.exists():
            raise FileNotFoundError(f"model file missing: {self.model_path}")

        import pickle

        with self.model_path.open("rb") as fp:
            models = pickle.load(fp)
        if not isinstance(models, list) or not models:
            raise ValueError("xgb_final_models.pkl must contain a non-empty model list")

        self.models = models
        self.features = self._load_feature_names()
        self._load_or_create_thresholds()
        self._load_or_create_medians()
        self._shap_explainer = None

    def _get_booster(self, model: Any) -> Any | None:
        if hasattr(model, "get_booster"):
            try:
                return model.get_booster()
            except Exception:
                return None

        # xgboost.Booster는 get_booster 없이 직접 predict를 제공
        if hasattr(model, "predict") and model.__class__.__name__.lower() == "booster":
            return model
        return None

    def _load_feature_names(self) -> list[str]:
        model = self.models[-1]
        model_features = None

        if hasattr(model, "feature_names") and model.feature_names:
            model_features = list(model.feature_names)
        else:
            booster = self._get_booster(model)
            if booster is not None and getattr(booster, "feature_names", None):
                model_features = list(booster.feature_names)

        if model_features:
            return [str(v) for v in model_features if str(v).strip()]

        if not self.feature_path.exists():
            raise FileNotFoundError(f"feature list missing: {self.feature_path}")
        feature_df = pd.read_csv(self.feature_path)
        if "feature" not in feature_df.columns:
            raise ValueError("xgb_selected_features.csv must include 'feature' column")
        return [str(v) for v in feature_df["feature"].tolist() if str(v).strip()]

    def _load_or_create_thresholds(self) -> None:
        if self.threshold_path.exists():
            threshold_df = pd.read_csv(self.threshold_path)
            data = {
                str(name).strip(): float(value)
                for name, value in zip(
                    threshold_df.get("thresh_name", []),
                    threshold_df.get("value", []),
                )
                if str(name).strip()
            }
            self.threshold_low = float(data.get("thresh_low", DEFAULT_THRESH_LOW))
            self.threshold_high = float(data.get("thresh_high", DEFAULT_THRESH_HIGH))
            self.threshold_critical = max(
                DEFAULT_THRESH_CRITICAL,
                self.threshold_high + 0.20,
            )
            return

        created = pd.DataFrame(
            [
                {"thresh_name": "thresh_low", "value": DEFAULT_THRESH_LOW},
                {"thresh_name": "thresh_high", "value": DEFAULT_THRESH_HIGH},
            ]
        )
        created.to_csv(self.threshold_path, index=False)
        self.threshold_low = DEFAULT_THRESH_LOW
        self.threshold_high = DEFAULT_THRESH_HIGH
        self.threshold_critical = DEFAULT_THRESH_CRITICAL

    def _load_or_create_medians(self) -> None:
        if self.median_path.exists():
            median_df = pd.read_csv(self.median_path)
            if "feature" in median_df.columns and "median" in median_df.columns:
                self.feature_medians = {
                    str(row["feature"]): _safe_float(row["median"])
                    for _, row in median_df.iterrows()
                    if str(row["feature"]).strip()
                }
                return

        if not self.feature_dataset_path.exists():
            raise FileNotFoundError(
                "features_final.csv is required to auto-generate feature_medians.csv"
            )

        feature_df = pd.read_csv(self.feature_dataset_path)
        medians: list[dict[str, Any]] = []
        mapped: dict[str, float] = {}
        for feature in self.features:
            value = 0.0
            if feature in feature_df.columns:
                numeric_series = pd.to_numeric(feature_df[feature], errors="coerce")
                if numeric_series.notna().any():
                    value = float(numeric_series.median())
            mapped[feature] = value
            medians.append({"feature": feature, "median": value})

        pd.DataFrame(medians).to_csv(self.median_path, index=False)
        self.feature_medians = mapped

    def _risk_level(self, risk_score: float) -> str:
        if risk_score >= self.threshold_critical:
            return "CRITICAL"
        if risk_score >= self.threshold_high:
            return "HIGH"
        if risk_score >= self.threshold_low:
            return "MEDIUM"
        return "LOW"

    def _recommendations(self, risk_level: str) -> list[str]:
        if risk_level == "CRITICAL":
            return [
                "즉시 담당의 통보",
                "Sepsis 번들 즉시 수행 검토",
                "ICU/전원 필요성 즉시 재평가",
            ]
        if risk_level == "HIGH":
            return [
                "담당의 재평가 요청",
                "바이탈/젖산 재측정",
                "항생제 및 감염원 재평가",
            ]
        if risk_level == "MEDIUM":
            return [
                "모니터링 강화",
                "혈액배양 및 감염원 추적",
            ]
        return ["정기 모니터링 유지"]

    def _build_feature_vector(self, raw_features: dict[str, Any]) -> pd.DataFrame:
        normalized_input = _normalize_feature_input(raw_features)
        row: dict[str, float] = {}
        for feature in self.features:
            row[feature] = float(
                normalized_input.get(feature, self.feature_medians.get(feature, 0.0))
            )
        return pd.DataFrame([row], columns=self.features)

    def _predict_one(self, model: Any, feature_vector: pd.DataFrame) -> float:
        if hasattr(model, "predict_proba"):
            pred = model.predict_proba(feature_vector)[:, 1]
            return _safe_float(pred[0], 0.0)

        booster = self._get_booster(model)
        if booster is not None:
            try:
                import xgboost as xgb
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "xgboost is required for booster prediction but not installed"
                ) from exc

            dmat = xgb.DMatrix(feature_vector, feature_names=self.features)
            pred = booster.predict(dmat)
            return _safe_float(pred[0], 0.0)

        if hasattr(model, "predict"):
            pred = model.predict(feature_vector)
            if isinstance(pred, (list, tuple, np.ndarray)):
                return _safe_float(pred[0], 0.0)
            return _safe_float(pred, 0.0)

        raise RuntimeError(f"unsupported model type for prediction: {type(model)}")

    def _build_contributing_factors(
        self,
        feature_vector: pd.DataFrame,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        model = self.models[-1]
        booster = self._get_booster(model)
        values = feature_vector.iloc[0].to_dict()

        if booster is not None:
            try:
                import shap
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "shap is required for contributing_factors but not installed"
                ) from exc

            if self._shap_explainer is None:
                self._shap_explainer = shap.TreeExplainer(booster)

            shap_values = self._shap_explainer.shap_values(feature_vector, check_additivity=False)
            if isinstance(shap_values, list):
                shap_values = shap_values[-1]
            shap_values_arr = np.asarray(shap_values, dtype=float)
            if shap_values_arr.ndim == 1:
                shap_row = shap_values_arr
            else:
                shap_row = shap_values_arr[0]

            if shap_row.shape[0] != len(self.features):
                raise RuntimeError("SHAP output length does not match feature length")

            top_indices = np.argsort(np.abs(shap_row))[-limit:][::-1]
            factors: list[dict[str, Any]] = []
            for idx in top_indices:
                feature = self.features[idx]
                shap_value = float(shap_row[idx])
                direction = "UP" if shap_value >= 0 else "DOWN"
                factors.append(
                    {
                        "feature": feature,
                        "value": _safe_float(values.get(feature), 0.0),
                        "contribution": float(round(abs(shap_value), 6)),
                        "shap": float(round(shap_value, 6)),
                        "direction": direction,
                        "interpretation": f"{feature} ({direction})",
                    }
                )
            return factors

        # booster를 사용할 수 없는 모델 유형에서는 importance*delta를 차선으로 사용
        if hasattr(model, "feature_importances_"):
            importances = np.asarray(model.feature_importances_, dtype=float)
            if importances.shape[0] != len(self.features):
                importances = np.ones(len(self.features), dtype=float)
        else:
            importances = np.ones(len(self.features), dtype=float)

        if np.all(importances == 0):
            importances = np.ones(len(self.features), dtype=float)

        factors = []
        for idx, feature in enumerate(self.features):
            value = _safe_float(values.get(feature), 0.0)
            baseline = _safe_float(self.feature_medians.get(feature), 0.0)
            delta = value - baseline
            signed_score = float(delta * importances[idx])
            abs_score = abs(signed_score)
            if abs_score <= 0:
                continue
            direction = "UP" if signed_score >= 0 else "DOWN"
            factors.append(
                {
                    "feature": feature,
                    "value": value,
                    "contribution": float(round(abs_score, 6)),
                    "shap": float(round(signed_score, 6)),
                    "direction": direction,
                    "interpretation": f"{feature} ({direction})",
                }
            )

        factors.sort(key=lambda item: item["contribution"], reverse=True)
        return factors[:limit]

    def predict(self, feature_snapshot: dict[str, Any]) -> InferenceOutput:
        if not self.models:
            raise RuntimeError("runtime not loaded")

        feature_vector = self._build_feature_vector(feature_snapshot)
        probs = [self._predict_one(model, feature_vector) for model in self.models]
        risk_score = float(np.clip(np.mean(probs), 0.0, 1.0))
        risk_level = self._risk_level(risk_score)
        factors = self._build_contributing_factors(feature_vector, limit=5)

        return InferenceOutput(
            risk_score=float(round(risk_score, 6)),
            risk_level=risk_level,
            contributing_factors=factors,
            recommendations=self._recommendations(risk_level),
            predicted_at=_utc_now_iso(),
            model_version=self.model_version,
        )
