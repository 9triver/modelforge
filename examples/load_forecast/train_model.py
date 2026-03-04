"""Train a GradientBoosting load forecast model.

Pipeline inputs (from version artifact directories):
  datasets/train.csv             <- 训练数据
  features/features.yaml         <- 特征定义（决定用哪些列作为 X）
  params/training_params.yaml    <- 超参数 + 数据切分配置

Pipeline outputs:
  weights/load_forecast_model.joblib  <- 模型权重
  metrics.json                        <- 评估指标
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.model_selection import train_test_split

TARGET = "load_mw"


def train(
    dataset_path="datasets/train.csv",
    feature_config_path="features/features.yaml",
    params_path="params/training_params.yaml",
    output_path="weights/load_forecast_model.joblib",
):
    # -- 1. 加载特征定义 --
    with open(feature_config_path) as f:
        feature_config = yaml.safe_load(f)
    features = [feat["name"] for feat in feature_config["features"]]
    print(f"[数据准备] 从 {feature_config_path} 加载特征定义")
    print(f"[数据准备] 特征 ({len(features)}): {features}")

    # -- 2. 加载训练数据，按特征定义选列 --
    data = pd.read_csv(dataset_path)
    X = data[features]
    y = data[TARGET]
    print(f"[数据准备] 从 {dataset_path} 加载数据: {len(data)} 行, 目标列: {TARGET}")

    # -- 3. 加载训练参数 --
    with open(params_path) as f:
        params_config = yaml.safe_load(f)
    model_params = params_config["parameters"]
    split = params_config.get("train_test_split", {})
    print(f"[训练配置] 从 {params_path} 加载参数")
    print(f"[训练配置] 算法: {params_config.get('algorithm', 'unknown')}")
    print(f"[训练配置] 参数: {model_params}")

    # -- 4. 切分数据 --
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=split.get("test_size", 0.2),
        shuffle=split.get("shuffle", False),
    )
    print(f"[训练配置] 切分: train={len(X_train)}, test={len(X_test)}")

    # -- 5. 训练模型 --
    model = GradientBoostingRegressor(**model_params)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    # -- 6. 评估 --
    metrics = {
        "mae": float(np.mean(np.abs(y_test - y_pred))),
        "rmse": float(np.sqrt(np.mean((y_test - y_pred) ** 2))),
        "mape": float(np.mean(np.abs((y_test - y_pred) / y_test)) * 100),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
    }
    print("[模型产出] 评估指标:")
    for k, v in metrics.items():
        print(f"  {k} = {v:.4f}" if isinstance(v, float) else f"  {k} = {v}")

    # -- 7. 保存模型权重 --
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_path)
    print(f"[模型产出] 权重已保存: {output_path}")

    with open("metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    return metrics


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Train load forecast model")
    p.add_argument("--dataset", default="datasets/train.csv")
    p.add_argument("--features", default="features/features.yaml")
    p.add_argument("--params", default="params/training_params.yaml")
    p.add_argument("--output", default="weights/load_forecast_model.joblib")
    args = p.parse_args()
    train(args.dataset, args.features, args.params, args.output)
