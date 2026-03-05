"""Feature importance comparison between East and North China models using SHAP.

Loads two trained models and their respective datasets, computes SHAP values,
and produces a comparison report identifying region-specific key features.

Usage:
  python feature_analysis.py \\
      --east-model east_model.joblib \\
      --east-data hua_dong_train.csv \\
      --east-features features_east.yaml \\
      --north-model north_model.joblib \\
      --north-data hua_bei_train.csv \\
      --north-features features_north.yaml
"""

import argparse
import json

import joblib
import numpy as np
import pandas as pd
import yaml


def load_features(path: str) -> list[str]:
    with open(path) as f:
        return [feat["name"] for feat in yaml.safe_load(f)["features"]]


def shap_importance(model, X: pd.DataFrame, feature_names: list[str],
                    n_samples: int = 500) -> dict[str, float]:
    """Compute mean |SHAP| for each feature."""
    try:
        import shap
        explainer = shap.TreeExplainer(model)
        sv = explainer.shap_values(X.iloc[:min(n_samples, len(X))])
        return {name: round(float(np.mean(np.abs(sv[:, i]))), 4)
                for i, name in enumerate(feature_names)}
    except ImportError:
        print("[警告] shap 未安装，使用 XGBoost gain importance")
        imp = model.get_booster().get_score(importance_type="gain")
        return {name: round(float(imp.get(f"f{i}", imp.get(name, 0))), 4)
                for i, name in enumerate(feature_names)}


def compare(east_imp: dict, north_imp: dict) -> dict:
    """Compare feature importance between regions."""
    all_features = sorted(set(list(east_imp.keys())
                              + list(north_imp.keys())))
    features = []
    for f in all_features:
        e_val = east_imp.get(f, 0)
        n_val = north_imp.get(f, 0)
        entry = {
            "name": f,
            "east_importance": e_val,
            "north_importance": n_val,
        }
        if e_val > 0 and n_val > 0:
            entry["ratio_north_vs_east"] = round(n_val / e_val, 2)
        features.append(entry)

    features.sort(
        key=lambda x: -(x["east_importance"] + x["north_importance"]),
    )

    # Identify features with large importance shifts
    east_dominant = [
        f["name"] for f in features
        if f["east_importance"] > 2 * f["north_importance"]
        and f["east_importance"] > 10
    ]
    north_dominant = [
        f["name"] for f in features
        if f["north_importance"] > 2 * f["east_importance"]
        and f["north_importance"] > 10
    ]
    top5 = [f["name"] for f in features[:5]]

    return {
        "features": features,
        "recommendation": {
            "east_dominant": east_dominant,
            "north_dominant": north_dominant,
            "shared_top_features": top5,
        },
    }


def main():
    p = argparse.ArgumentParser(description="SHAP feature importance comparison")
    p.add_argument("--east-model", required=True)
    p.add_argument("--east-data", required=True)
    p.add_argument("--east-features", required=True)
    p.add_argument("--north-model", required=True)
    p.add_argument("--north-data", required=True)
    p.add_argument("--north-features", required=True)
    p.add_argument("--output", default="feature_comparison.json")
    args = p.parse_args()

    # Load East
    east_feat_names = load_features(args.east_features)
    east_data = pd.read_csv(args.east_data)
    east_available = [f for f in east_feat_names if f in east_data.columns]
    east_model = joblib.load(args.east_model)

    # Load North
    north_feat_names = load_features(args.north_features)
    north_data = pd.read_csv(args.north_data)
    north_available = [f for f in north_feat_names if f in north_data.columns]
    north_model = joblib.load(args.north_model)

    print("=" * 60)
    print("SHAP Feature Importance Analysis")
    print("=" * 60)

    print(f"\n华东特征: {east_available}")
    east_imp = shap_importance(east_model, east_data[east_available], east_available)
    print("华东重要性:")
    for name, val in sorted(east_imp.items(), key=lambda x: -x[1]):
        print(f"  {name}: {val:.4f}")

    print(f"\n华北特征: {north_available}")
    north_imp = shap_importance(north_model, north_data[north_available], north_available)
    print("华北重要性:")
    for name, val in sorted(north_imp.items(), key=lambda x: -x[1]):
        print(f"  {name}: {val:.4f}")

    report = compare(east_imp, north_imp)

    rec = report['recommendation']
    print("\n建议:")
    print(f"  华东主导特征: {rec['east_dominant']}")
    print(f"  华北主导特征: {rec['north_dominant']}")
    print(f"  共享关键特征: {rec['shared_top_features']}")

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"\n报告已保存: {args.output}")

    return report


if __name__ == "__main__":
    main()
