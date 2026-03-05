"""Unified XGBoost trainer for load forecasting with warm-start support.

Pipeline inputs (from version artifact directories):
  datasets/train.csv             <- Training data
  features/features.yaml         <- Feature definitions (select columns for X)
  params/training_params.yaml    <- Hyperparameters + split config

Pipeline outputs:
  weights/model.joblib           <- Model weights
  metrics.json                   <- Evaluation metrics
  feature_importance.json        <- SHAP-based feature importance

CLI contract (ModelForge runner compatible):
  python code/train.py \\
      --dataset datasets/train.csv \\
      --features features/features.yaml \\
      --params params/training_params.yaml \\
      --output weights/model.joblib \\
      [--warm-start weights/base_model.joblib]
"""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
import yaml
from sklearn.model_selection import train_test_split

TARGET = "load_mw"


def load_features(path: str) -> list[str]:
    """Load feature names from features.yaml."""
    with open(path) as f:
        config = yaml.safe_load(f)
    return [feat["name"] for feat in config["features"]]


def load_params(path: str) -> tuple[dict, dict, dict]:
    """Load training params, split config, and warm_start config."""
    with open(path) as f:
        config = yaml.safe_load(f)
    model_params = dict(config["parameters"])
    split_config = config.get("train_test_split", {"test_size": 0.2, "shuffle": False})
    warm_start_config = config.get("warm_start", {"enabled": False})
    return model_params, split_config, warm_start_config


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    """Compute regression metrics."""
    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mape = float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100)
    return {"mae": round(mae, 2), "rmse": round(rmse, 2), "mape": round(mape, 2)}


def compute_feature_importance(model, X_test: pd.DataFrame, feature_names: list[str]) -> dict:
    """Compute SHAP-based feature importance. Falls back to gain if shap unavailable."""
    try:
        import shap
        explainer = shap.TreeExplainer(model)
        sample = X_test.iloc[:min(500, len(X_test))]
        shap_values = explainer.shap_values(sample)
        importance = {}
        for i, name in enumerate(feature_names):
            importance[name] = round(float(np.mean(np.abs(shap_values[:, i]))), 4)
        return {"method": "shap", "importance": importance}
    except ImportError:
        print("[警告] shap 未安装，使用 XGBoost 内置特征重要性")
        imp = model.get_booster().get_score(importance_type="gain")
        importance = {}
        for i, name in enumerate(feature_names):
            importance[name] = round(float(imp.get(f"f{i}", imp.get(name, 0))), 4)
        return {"method": "gain", "importance": importance}


def train(
    dataset_path: str = "datasets/train.csv",
    feature_config_path: str = "features/features.yaml",
    params_path: str = "params/training_params.yaml",
    output_path: str = "weights/model.joblib",
    warm_start_path: str | None = None,
) -> dict:
    # -- 1. Load feature definitions --
    features = load_features(feature_config_path)
    print(f"[数据准备] 特征 ({len(features)}): {features}")

    # -- 2. Load data, handle missing features gracefully --
    data = pd.read_csv(dataset_path)
    available = [f for f in features if f in data.columns]
    missing = [f for f in features if f not in data.columns]
    if missing:
        print(f"[警告] 数据中缺少特征: {missing}，将跳过")
    X = data[available]
    y = data[TARGET]
    print(f"[数据准备] {len(data)} 行, {len(available)} 特征, 目标: {TARGET}")

    # -- 3. Load params --
    model_params, split_config, warm_config = load_params(params_path)
    print(f"[训练配置] 参数: {model_params}")

    # -- 4. Split --
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size=split_config.get("test_size", 0.2),
        shuffle=split_config.get("shuffle", False),
    )
    print(f"[训练配置] 切分: train={len(X_train)}, test={len(X_test)}")

    # -- 5. Resolve warm-start model --
    ws_path = warm_start_path
    if not ws_path and warm_config.get("enabled"):
        ws_path = warm_config.get("base_model")

    if ws_path and Path(ws_path).exists():
        print(f"[迁移学习] 加载基础模型: {ws_path}")
        base_model = joblib.load(ws_path)

        # Align features: base model may expect different columns
        base_features = None
        if hasattr(base_model, "get_booster"):
            base_features = base_model.get_booster().feature_names
        elif hasattr(base_model, "feature_names_in_"):
            base_features = list(base_model.feature_names_in_)

        if base_features and set(base_features) != set(X_train.columns):
            added = [f for f in base_features if f not in X_train.columns]
            dropped = [f for f in X_train.columns if f not in base_features]
            if added:
                print(f"[迁移学习] 补零对齐特征: {added}")
                for col in added:
                    X_train[col] = 0.0
                    X_test[col] = 0.0
            if dropped:
                print(f"[迁移学习] 忽略基础模型未使用的特征: {dropped}")
            X_train = X_train[base_features]
            X_test = X_test[base_features]
            available = base_features
            print(f"[迁移学习] 对齐后特征 ({len(available)}): {available}")

        n_additional = model_params.pop("n_estimators", 100)
        model = xgb.XGBRegressor(
            n_estimators=n_additional, **model_params,
        )
        booster = (base_model.get_booster()
                   if hasattr(base_model, "get_booster")
                   else ws_path)
        model.fit(
            X_train, y_train,
            xgb_model=booster,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )
        print(f"[迁移学习] 在基础模型上继续训练 {n_additional} 轮")
    else:
        if ws_path:
            print(f"[警告] 基础模型不存在: {ws_path}，从头训练")
        model = xgb.XGBRegressor(**model_params)
        model.fit(
            X_train, y_train,
            eval_set=[(X_test, y_test)],
            verbose=False,
        )

    y_pred = model.predict(X_test)

    # -- 6. Metrics --
    metrics = compute_metrics(y_test.values, y_pred)
    metrics["train_samples"] = len(X_train)
    metrics["test_samples"] = len(X_test)
    metrics["features_used"] = available
    metrics["warm_start"] = bool(ws_path and Path(ws_path).exists())
    print("[模型产出] 评估指标:")
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k} = {v:.4f}")
        else:
            print(f"  {k} = {v}")

    # -- 7. Feature importance --
    fi = compute_feature_importance(model, X_test, available)
    print(f"[模型产出] 特征重要性 ({fi['method']}):")
    for name, val in sorted(fi["importance"].items(), key=lambda x: -x[1]):
        print(f"  {name}: {val:.4f}")

    # -- 8. Save --
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_path)
    print(f"[模型产出] 权重已保存: {output_path}")

    with open("metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    with open("feature_importance.json", "w") as f:
        json.dump(fi, f, indent=2, ensure_ascii=False)

    return metrics


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Train XGBoost load forecast model")
    p.add_argument("--dataset", default="datasets/train.csv")
    p.add_argument("--features", default="features/features.yaml")
    p.add_argument("--params", default="params/training_params.yaml")
    p.add_argument("--output", default="weights/model.joblib")
    p.add_argument("--warm-start", default=None, dest="warm_start",
                   help="Path to base model for warm-start/fine-tuning")
    args = p.parse_args()
    train(args.dataset, args.features, args.params, args.output, args.warm_start)
