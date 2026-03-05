from typing import Any

from pydantic import BaseModel


class MetricComparison(BaseModel):
    name: str
    training_value: float | None = None
    trial_value: float
    delta_percent: float | None = None  # (trial - training) / training * 100


class FeatureImportance(BaseModel):
    name: str
    importance: float


class DriftFeature(BaseModel):
    name: str
    psi: float
    psi_severity: str  # none / moderate / significant
    ref_mean: float
    ref_std: float
    tgt_mean: float
    tgt_std: float


class Recommendation(BaseModel):
    type: str  # feature_drift / importance_shift / retrain
    severity: str  # info / warning / critical
    message: str


class Diagnosis(BaseModel):
    feature_importance: list[FeatureImportance]
    drift_report: list[DriftFeature]
    recommendations: list[Recommendation]


class TrialEvaluationResponse(BaseModel):
    trial_metrics: dict[str, float]
    training_metrics: dict[str, Any]
    comparison: list[MetricComparison]
    verdict: str  # compatible / moderate_degradation / severe_degradation
    diagnosis: Diagnosis | None = None
    sample_count: int
    features_matched: int
    features_total: int
