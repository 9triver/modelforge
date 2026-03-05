"""Trial evaluation: load model temporarily, predict on user CSV, compare metrics.

Extended with diagnosis: SHAP feature importance + PSI/KS drift detection
to tell users WHY the model underperforms and WHAT to fix.
"""

import math
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from fastapi import HTTPException

from modelforge.services.inference import SklearnRunner
from modelforge.store import ModelStore


def trial_evaluate(
    store: ModelStore,
    model_id: str,
    version_id: str,
    csv_bytes: bytes,
) -> dict:
    """Run trial evaluation of a model version against user-uploaded CSV data.

    Returns comparison of trial metrics vs training metrics with a verdict,
    plus diagnosis (SHAP importance + drift detection + recommendations).
    """
    slug, version_str, vdir = store._resolve_version_dir(model_id, version_id)
    version_data = store.get_version(model_id, version_id)

    if version_data.get("stage") == "draft":
        raise HTTPException(400, "Cannot evaluate a draft version (not yet trained)")
    if not version_data.get("file_path"):
        raise HTTPException(400, "Version has no model file")

    # Parse CSV
    try:
        df = pd.read_csv(BytesIO(csv_bytes))
    except Exception as e:
        raise HTTPException(400, f"Failed to parse CSV: {e}")
    if df.empty:
        raise HTTPException(400, "CSV file is empty")

    # Resolve target column
    target = _resolve_target(store, model_id, vdir)
    if target not in df.columns:
        raise HTTPException(
            400,
            f"Target column '{target}' not found in CSV. "
            f"Available columns: {list(df.columns)}",
        )

    # Resolve feature columns
    feature_names = _resolve_features(vdir)
    if not feature_names:
        feature_names = [c for c in df.columns if c != target]

    matched_features = [f for f in feature_names if f in df.columns]
    if not matched_features:
        raise HTTPException(
            400,
            f"No matching feature columns found in CSV. "
            f"Expected: {feature_names[:5]}...",
        )

    # Load model temporarily
    file_path = vdir / version_data["file_path"]
    if not file_path.exists():
        raise HTTPException(400, "Model file not found on storage")

    runner = SklearnRunner()
    try:
        runner.load(file_path)

        # Use the model's own feature names as authoritative source
        # (handles warm-start alignment, feature reordering, etc.)
        model_features = _get_model_features(runner)
        if model_features:
            matched_features = model_features
            # Pad missing columns with 0 (e.g. warm-start aligned features)
            for col in matched_features:
                if col not in df.columns:
                    df[col] = 0.0

        X_df = df[matched_features]
        y_true = df[target].values
        y_pred = runner.predict(X_df.values.tolist())

        # SHAP feature importance (while model is loaded)
        feature_importance = _shap_importance(runner, X_df, matched_features)
    finally:
        runner.unload()

    # Compute trial metrics
    trial_metrics = _compute_metrics(y_true, y_pred)

    # Compare with training metrics
    training_metrics = version_data.get("metrics") or {}
    comparison = _compare_metrics(training_metrics, trial_metrics)

    # Determine verdict
    verdict = _determine_verdict(comparison)

    # Diagnosis: drift detection + recommendations
    diagnosis = None
    if verdict != "compatible":
        drift_report = _drift_detection(vdir, df, matched_features, target)
        recommendations = _generate_recommendations(
            feature_importance, drift_report, verdict,
        )
        diagnosis = {
            "feature_importance": feature_importance,
            "drift_report": drift_report,
            "recommendations": recommendations,
        }

    return {
        "trial_metrics": trial_metrics,
        "training_metrics": training_metrics,
        "comparison": comparison,
        "verdict": verdict,
        "diagnosis": diagnosis,
        "sample_count": len(df),
        "features_matched": len(matched_features),
        "features_total": len(feature_names),
    }


# ── Target / Feature resolution ──


def _resolve_target(store: ModelStore, model_id: str, vdir: Path) -> str:
    """Determine the target column name from pipeline or features config."""
    pipeline = store.get_pipeline(model_id)
    if pipeline:
        target = pipeline.get("data_prep", {}).get("target")
        if target:
            return target

    features_path = vdir / "features" / "features.yaml"
    if features_path.exists():
        with open(features_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        if data.get("target"):
            return data["target"]

    return "load_mw"


def _get_model_features(runner: SklearnRunner) -> list[str] | None:
    """Extract feature names from the loaded model object."""
    model = runner._model
    if model is None:
        return None
    # XGBoost models
    if hasattr(model, "get_booster"):
        names = model.get_booster().feature_names
        if names:
            return list(names)
    # Sklearn models with feature_names_in_
    if hasattr(model, "feature_names_in_"):
        return list(model.feature_names_in_)
    return None


def _resolve_features(vdir: Path) -> list[str]:
    """Read feature names from features directory.

    Tries features.yaml first, then falls back to any .yaml file.
    """
    features_dir = vdir / "features"
    if not features_dir.exists():
        return []

    # Try features.yaml first (convention)
    candidates = [features_dir / "features.yaml"]
    # Fallback: any other yaml file
    if features_dir.exists():
        for f in sorted(features_dir.iterdir()):
            if f.suffix in (".yaml", ".yml") and f not in candidates:
                candidates.append(f)

    for features_path in candidates:
        if not features_path.exists():
            continue
        with open(features_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        features = data.get("features", [])
        names = [feat["name"] for feat in features
                 if isinstance(feat, dict) and "name" in feat]
        if names:
            return names
    return []


# ── Metrics ──


def _compute_metrics(y_true, y_pred) -> dict[str, float]:
    """Compute MAE, RMSE, and MAPE."""
    n = len(y_true)
    if n == 0:
        return {}

    mae = sum(abs(a - p) for a, p in zip(y_true, y_pred)) / n
    rmse = math.sqrt(sum((a - p) ** 2 for a, p in zip(y_true, y_pred)) / n)

    mape_values = [abs((a - p) / a) for a, p in zip(y_true, y_pred) if a != 0]
    mape = (sum(mape_values) / len(mape_values) * 100) if mape_values else None

    result = {
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
    }
    if mape is not None:
        result["mape"] = round(mape, 4)
    return result


def _compare_metrics(training: dict, trial: dict) -> list[dict]:
    """Compare trial metrics against training metrics."""
    all_keys = set(trial.keys())
    if training:
        all_keys |= {k for k in training if isinstance(training.get(k), (int, float))}

    comparison = []
    for key in sorted(all_keys):
        trial_val = trial.get(key)
        if trial_val is None:
            continue
        train_val = training.get(key) if training else None
        if train_val is not None and not isinstance(train_val, (int, float)):
            train_val = None

        delta = None
        if train_val is not None and train_val != 0:
            delta = round((trial_val - train_val) / abs(train_val) * 100, 2)

        comparison.append({
            "name": key,
            "training_value": round(float(train_val), 4) if train_val is not None else None,
            "trial_value": round(float(trial_val), 4),
            "delta_percent": delta,
        })
    return comparison


def _determine_verdict(comparison: list[dict]) -> str:
    """Determine compatibility verdict based on metric deltas."""
    metric_priority = ["mape", "rmse", "mae"]
    for metric_name in metric_priority:
        for item in comparison:
            if item["name"] == metric_name and item["delta_percent"] is not None:
                delta = item["delta_percent"]
                if delta <= 20:
                    return "compatible"
                elif delta <= 50:
                    return "moderate_degradation"
                else:
                    return "severe_degradation"
    return "compatible"


# ── SHAP Feature Importance ──


def _shap_importance(
    runner: SklearnRunner, X_df: pd.DataFrame, feature_names: list[str],
    n_samples: int = 500,
) -> list[dict]:
    """Compute mean |SHAP| for each feature on the user's data."""
    model = runner._model
    if model is None:
        return [{"name": f, "importance": 0.0} for f in feature_names]

    sample = X_df.iloc[:min(n_samples, len(X_df))]

    try:
        import shap
        explainer = shap.TreeExplainer(model)
        sv = explainer.shap_values(sample)
        importances = {
            name: round(float(np.mean(np.abs(sv[:, i]))), 4)
            for i, name in enumerate(feature_names)
        }
    except Exception:
        # Fallback: use model's built-in feature importance if available
        try:
            raw_imp = model.feature_importances_
            importances = {
                name: round(float(raw_imp[i]), 4)
                for i, name in enumerate(feature_names)
                if i < len(raw_imp)
            }
        except Exception:
            return [{"name": f, "importance": 0.0} for f in feature_names]

    result = [
        {"name": name, "importance": importances.get(name, 0.0)}
        for name in feature_names
    ]
    result.sort(key=lambda x: -x["importance"])
    return result


# ── Drift Detection (PSI) ──


def _compute_psi(reference: np.ndarray, target: np.ndarray, bins: int = 10) -> float:
    """Population Stability Index between two distributions."""
    breakpoints = np.percentile(reference, np.linspace(0, 100, bins + 1))
    breakpoints = np.unique(breakpoints)
    if len(breakpoints) < 2:
        return 0.0

    ref_counts = np.histogram(reference, bins=breakpoints)[0]
    tgt_counts = np.histogram(target, bins=breakpoints)[0]

    eps = 1e-6
    ref_pct = ref_counts / len(reference) + eps
    tgt_pct = tgt_counts / len(target) + eps

    return float(np.sum((tgt_pct - ref_pct) * np.log(tgt_pct / ref_pct)))


def _drift_detection(
    vdir: Path,
    user_df: pd.DataFrame,
    features: list[str],
    target: str,
) -> list[dict]:
    """Compare feature distributions between training data and user's CSV."""
    # Find training CSV
    train_csv = _find_training_csv(vdir)
    if train_csv is None:
        return []

    try:
        ref_df = pd.read_csv(train_csv)
    except Exception:
        return []

    # Analyze features + target
    columns_to_check = [f for f in features if f in ref_df.columns and f in user_df.columns]
    if target in ref_df.columns and target in user_df.columns:
        columns_to_check.append(target)

    results = []
    for col in columns_to_check:
        ref = ref_df[col].dropna().values.astype(float)
        tgt = user_df[col].dropna().values.astype(float)
        if len(ref) == 0 or len(tgt) == 0:
            continue

        psi = _compute_psi(ref, tgt)
        severity = "none" if psi < 0.1 else "moderate" if psi < 0.25 else "significant"

        results.append({
            "name": col,
            "psi": round(psi, 4),
            "psi_severity": severity,
            "ref_mean": round(float(np.mean(ref)), 2),
            "ref_std": round(float(np.std(ref)), 2),
            "tgt_mean": round(float(np.mean(tgt)), 2),
            "tgt_std": round(float(np.std(tgt)), 2),
        })

    results.sort(key=lambda x: -x["psi"])
    return results


def _find_training_csv(vdir: Path) -> Path | None:
    """Find the training CSV in version datasets/."""
    datasets_dir = vdir / "datasets"
    if not datasets_dir.exists():
        return None
    for name in ("train.csv", "training.csv", "data.csv"):
        path = datasets_dir / name
        if path.exists():
            return path
    # Fallback: first CSV found
    for f in datasets_dir.iterdir():
        if f.suffix == ".csv":
            return f
    return None


# ── Recommendations ──


def _generate_recommendations(
    feature_importance: list[dict],
    drift_report: list[dict],
    verdict: str,
) -> list[dict]:
    """Generate actionable recommendations based on diagnosis."""
    recs = []

    # Drift-based recommendations
    significant_drifts = [d for d in drift_report if d["psi_severity"] == "significant"]
    moderate_drifts = [d for d in drift_report if d["psi_severity"] == "moderate"]

    if significant_drifts:
        names = ", ".join(d["name"] for d in significant_drifts[:3])
        recs.append({
            "type": "feature_drift",
            "severity": "critical",
            "message": f"特征分布显著偏移: {names}。必须使用本地数据重新训练。",
        })

    if moderate_drifts:
        names = ", ".join(d["name"] for d in moderate_drifts[:3])
        recs.append({
            "type": "feature_drift",
            "severity": "warning",
            "message": f"特征分布中度偏移: {names}。建议补充本地数据微调。",
        })

    # Importance-based recommendations
    if feature_importance:
        top3 = [f["name"] for f in feature_importance[:3]]
        low_importance = [
            f["name"] for f in feature_importance
            if f["importance"] < 1.0 and f["importance"] > 0
        ]
        if top3:
            recs.append({
                "type": "importance_shift",
                "severity": "info",
                "message": f"模型在您数据上最依赖的特征: {', '.join(top3)}。"
                           f"请确保这些特征的数据质量。",
            })
        if low_importance:
            recs.append({
                "type": "importance_shift",
                "severity": "info",
                "message": f"低重要性特征: {', '.join(low_importance[:3])}。"
                           f"可考虑在适配时移除以简化模型。",
            })

    # General adaptation recommendation
    if verdict == "severe_degradation":
        recs.append({
            "type": "retrain",
            "severity": "critical",
            "message": "建议 Fork 后使用本地数据从源模型 Fine-tune（迁移学习），"
                       "比从零训练收敛更快且保留源模型的共享知识。",
        })
    elif verdict == "moderate_degradation":
        recs.append({
            "type": "retrain",
            "severity": "warning",
            "message": "建议 Fork 后调整超参数并用本地数据微调，"
                       "或上传本地数据创建新版本重新训练。",
        })

    return recs
