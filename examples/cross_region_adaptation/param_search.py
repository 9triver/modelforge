"""Optuna-based hyperparameter search for North China adaptation.

Starts from East China's best params as baseline and searches around them.
Supports warm-start from the East model for faster convergence.

Usage:
  python param_search.py \\
      --dataset hua_bei_train.csv \\
      --features features_north.yaml \\
      --base-params training_params_east.yaml \\
      [--base-model east_model.joblib] \\
      [--n-trials 50] \\
      --output training_params_optimized.yaml
"""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml
import xgboost as xgb
from sklearn.model_selection import train_test_split

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
except ImportError:
    optuna = None

TARGET = "load_mw"


def load_features(path: str) -> list[str]:
    with open(path) as f:
        return [feat["name"] for feat in yaml.safe_load(f)["features"]]


def load_base_params(path: str) -> dict:
    with open(path) as f:
        return dict(yaml.safe_load(f)["parameters"])


def objective(trial, X_train, y_train, X_val, y_val,
              base_params, base_model_path=None):
    """Optuna objective: search around base params."""
    params = {
        "n_estimators": trial.suggest_int(
            "n_estimators",
            max(50, base_params.get("n_estimators", 200) - 100),
            base_params.get("n_estimators", 200) + 200,
        ),
        "max_depth": trial.suggest_int(
            "max_depth",
            max(3, base_params.get("max_depth", 6) - 2),
            base_params.get("max_depth", 6) + 3,
        ),
        "learning_rate": trial.suggest_float(
            "learning_rate",
            base_params.get("learning_rate", 0.1) * 0.3,
            base_params.get("learning_rate", 0.1) * 2.0,
            log=True,
        ),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "reg_alpha": trial.suggest_float("reg_alpha", 0.001, 1.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 5.0),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
        "random_state": 42,
    }

    model = xgb.XGBRegressor(**params)
    fit_kwargs = {"eval_set": [(X_val, y_val)], "verbose": False}

    if base_model_path and Path(base_model_path).exists():
        base = joblib.load(base_model_path)
        fit_kwargs["xgb_model"] = (
            base.get_booster() if hasattr(base, "get_booster") else base_model_path
        )

    model.fit(X_train, y_train, **fit_kwargs)
    y_pred = model.predict(X_val)
    mape = float(np.mean(np.abs((y_val - y_pred) / y_val)) * 100)
    return mape


def main():
    p = argparse.ArgumentParser(description="Optuna hyperparameter search")
    p.add_argument("--dataset", required=True)
    p.add_argument("--features", required=True)
    p.add_argument("--base-params", required=True, dest="base_params")
    p.add_argument("--base-model", default=None, dest="base_model")
    p.add_argument("--n-trials", type=int, default=50, dest="n_trials")
    p.add_argument("--output", default="training_params_optimized.yaml")
    args = p.parse_args()

    if optuna is None:
        print("[错误] optuna 未安装，请运行: pip install optuna")
        return None

    # Load data
    feat_names = load_features(args.features)
    data = pd.read_csv(args.dataset)
    available = [f for f in feat_names if f in data.columns]
    X = data[available]
    y = data[TARGET]

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, shuffle=False,
    )

    base_params = load_base_params(args.base_params)

    print("=" * 60)
    print("Optuna Hyperparameter Search")
    print("=" * 60)
    print(f"数据: {len(X_train)} train, {len(X_val)} val")
    print(f"特征: {available}")
    print(f"基础参数: {base_params}")
    print(f"Warm-start: {args.base_model or 'None'}")
    print(f"Trials: {args.n_trials}\n")

    # Baseline
    base_model = xgb.XGBRegressor(**base_params)
    base_model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    base_pred = base_model.predict(X_val)
    base_mape = float(np.mean(np.abs((y_val - base_pred) / y_val)) * 100)
    print(f"基础参数 MAPE: {base_mape:.2f}%\n")

    # Search
    study = optuna.create_study(direction="minimize")

    # Enqueue base params as first trial (warm start for the search itself)
    study.enqueue_trial({
        "n_estimators": base_params.get("n_estimators", 200),
        "max_depth": base_params.get("max_depth", 6),
        "learning_rate": base_params.get("learning_rate", 0.1),
        "subsample": base_params.get("subsample", 0.8),
        "colsample_bytree": base_params.get("colsample_bytree", 0.8),
        "reg_alpha": base_params.get("reg_alpha", 0.1),
        "reg_lambda": base_params.get("reg_lambda", 1.0),
        "min_child_weight": base_params.get("min_child_weight", 1),
    })

    study.optimize(
        lambda trial: objective(
            trial, X_train, y_train, X_val, y_val,
            base_params, args.base_model,
        ),
        n_trials=args.n_trials,
    )

    best = study.best_trial
    print(f"\n最优 Trial #{best.number}: MAPE = {best.value:.2f}%")
    print(f"改进: {base_mape:.2f}% -> {best.value:.2f}% "
          f"({base_mape - best.value:+.2f}%)")
    print(f"参数: {best.params}")

    # Save optimized params
    optimized = {
        "algorithm": "XGBRegressor",
        "framework": "xgboost",
        "parameters": {k: (int(v) if isinstance(v, int) else round(v, 6))
                       for k, v in best.params.items()},
        "train_test_split": {"test_size": 0.2, "shuffle": False},
        "source": "optuna_search",
        "search_details": {
            "n_trials": args.n_trials,
            "best_trial": best.number,
            "base_mape": round(base_mape, 2),
            "optimized_mape": round(best.value, 2),
        },
    }
    optimized["parameters"]["random_state"] = 42

    with open(args.output, "w") as f:
        yaml.dump(optimized, f, default_flow_style=False, allow_unicode=True)
    print(f"\n优化参数已保存: {args.output}")

    return optimized


if __name__ == "__main__":
    main()
