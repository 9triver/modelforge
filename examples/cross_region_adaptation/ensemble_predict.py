"""Multi-model ensemble for cross-region predictions.

Supports:
1. Weighted average: w_east * east_pred + w_north * north_pred
2. Season-based routing: winter -> north model, summer -> east model

Usage:
  python ensemble_predict.py \\
      --east-model east_model.joblib \\
      --north-model north_model.joblib \\
      --data hua_bei_train.csv \\
      --east-features features_east.yaml \\
      --north-features features_north.yaml \\
      [--method weighted_average|season_router] \\
      [--weights 0.3,0.7]
"""

import argparse
import json

import joblib
import numpy as np
import pandas as pd
import yaml

TARGET = "load_mw"


def load_features(path: str) -> list[str]:
    with open(path) as f:
        return [feat["name"] for feat in yaml.safe_load(f)["features"]]


def predict_with_model(model, data: pd.DataFrame, features: list[str]) -> np.ndarray:
    """Predict using model with available features, padding missing ones with 0."""
    aligned = data.reindex(columns=features, fill_value=0)
    return model.predict(aligned)


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mape = float(np.mean(np.abs((y_true - y_pred) / y_true)) * 100)
    return {"mae": round(mae, 2), "rmse": round(rmse, 2), "mape": round(mape, 2)}


class WeightedEnsemble:
    """Simple weighted average of model predictions."""

    def __init__(self, weights: tuple[float, ...] = (0.3, 0.7)):
        self.weights = weights

    def predict(self, predictions_list: list[np.ndarray]) -> np.ndarray:
        result = np.zeros_like(predictions_list[0])
        for pred, w in zip(predictions_list, self.weights):
            result += w * pred
        return result


class SeasonRouter:
    """Route to different models based on month (season).

    Winter months: trust north model more (heating expertise)
    Summer months: trust east model more (AC expertise)
    Shoulder seasons: equal weight
    """

    def __init__(self, heating_months=(11, 12, 1, 2, 3),
                 cooling_months=(6, 7, 8, 9)):
        self.heating_months = set(heating_months)
        self.cooling_months = set(cooling_months)

    def predict(self, months: np.ndarray,
                east_preds: np.ndarray, north_preds: np.ndarray) -> np.ndarray:
        result = np.zeros_like(east_preds)
        for i, m in enumerate(months):
            if m in self.heating_months:
                result[i] = 0.2 * east_preds[i] + 0.8 * north_preds[i]
            elif m in self.cooling_months:
                result[i] = 0.6 * east_preds[i] + 0.4 * north_preds[i]
            else:
                result[i] = 0.5 * east_preds[i] + 0.5 * north_preds[i]
        return result


def evaluate(data: pd.DataFrame, east_model, north_model,
             east_features: list[str], north_features: list[str],
             method: str = "weighted_average",
             weights: tuple[float, ...] = (0.3, 0.7)) -> dict:
    """Run ensemble evaluation."""
    y = data[TARGET].values
    east_preds = predict_with_model(east_model, data, east_features)
    north_preds = predict_with_model(north_model, data, north_features)

    if method == "weighted_average":
        ensemble = WeightedEnsemble(weights)
        y_pred = ensemble.predict([east_preds, north_preds])
    elif method == "season_router":
        router = SeasonRouter()
        y_pred = router.predict(data["month"].values, east_preds, north_preds)
    else:
        raise ValueError(f"Unknown method: {method}")

    return {
        "ensemble": {
            **compute_metrics(y, y_pred),
            "method": method,
        },
        "individual": {
            "east_model": compute_metrics(y, east_preds),
            "north_model": compute_metrics(y, north_preds),
        },
    }


def main():
    p = argparse.ArgumentParser(description="Multi-model ensemble evaluation")
    p.add_argument("--east-model", required=True)
    p.add_argument("--north-model", required=True)
    p.add_argument("--data", required=True, help="Target domain CSV for evaluation")
    p.add_argument("--east-features", required=True)
    p.add_argument("--north-features", required=True)
    p.add_argument("--method", default="both",
                   choices=["weighted_average", "season_router", "both"])
    p.add_argument("--weights", default="0.3,0.7",
                   help="Comma-separated weights for weighted_average")
    p.add_argument("--output", default="ensemble_results.json")
    args = p.parse_args()

    east_model = joblib.load(args.east_model)
    north_model = joblib.load(args.north_model)
    data = pd.read_csv(args.data)
    east_features = load_features(args.east_features)
    north_features = load_features(args.north_features)
    weights = tuple(float(w) for w in args.weights.split(","))

    print("=" * 60)
    print("Multi-Model Ensemble Evaluation")
    print("=" * 60)
    print(f"数据: {args.data} ({len(data)} rows)")

    results = {}

    methods = (["weighted_average", "season_router"]
               if args.method == "both"
               else [args.method])

    for method in methods:
        r = evaluate(data, east_model, north_model,
                     east_features, north_features,
                     method=method, weights=weights)
        results[method] = r

        print(f"\n--- {method} ---")
        print(f"  华东模型单独: MAPE={r['individual']['east_model']['mape']:.2f}%")
        print(f"  华北模型单独: MAPE={r['individual']['north_model']['mape']:.2f}%")
        print(f"  融合结果:     MAPE={r['ensemble']['mape']:.2f}%")

    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n结果已保存: {args.output}")

    return results


if __name__ == "__main__":
    main()
