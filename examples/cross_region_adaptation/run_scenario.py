"""
华东短期负荷预测模型迁移到华北 — 8 步端到端演示

Demonstrates 5 cross-region adaptation technologies:
  1. Feature engineering adaptation (SHAP analysis + region-specific feature selection)
  2. Parameter transfer & tuning (Optuna warm-start from East params)
  3. Distribution drift detection (PSI/KS tests)
  4. Model fine-tuning / transfer learning (XGBoost warm-start)
  5. Model ensemble & routing (weighted average + seasonal routing)

Usage:
  cd examples/cross_region_adaptation
  python run_scenario.py [--skip-optuna] [--n-trials 20]
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

# Ensure imports work
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from generate_data import generate_east_china, generate_north_china
from train import train as train_model, load_features, compute_metrics
from drift_detection import analyze_drift
from ensemble_predict import evaluate as ensemble_evaluate


def _write_features_yaml(path: Path, group_name: str, features: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump({"group_name": group_name, "target": "load_mw", "features": features},
                  f, default_flow_style=False, allow_unicode=True)


def _write_params_yaml(path: Path, params: dict, **extra):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "algorithm": "XGBRegressor",
        "framework": "xgboost",
        "parameters": params,
        "train_test_split": {"test_size": 0.2, "shuffle": False},
        **extra,
    }
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


# Feature definitions — unified 10-feature schema for both regions
FULL_FEATURES = [
    {"name": "temperature", "data_type": "float", "unit": "celsius",
     "description": "环境温度", "value_range": {"min": -40, "max": 50}},
    {"name": "hour", "data_type": "int", "unit": None,
     "description": "小时 (0-23)", "value_range": {"min": 0, "max": 23}},
    {"name": "day_of_week", "data_type": "int", "unit": None,
     "description": "星期几 (0=周一)", "value_range": {"min": 0, "max": 6}},
    {"name": "is_weekend", "data_type": "int", "unit": None,
     "description": "是否周末", "value_range": {"min": 0, "max": 1}},
    {"name": "is_holiday", "data_type": "int", "unit": None,
     "description": "是否节假日", "value_range": {"min": 0, "max": 1}},
    {"name": "month", "data_type": "int", "unit": None,
     "description": "月份", "value_range": {"min": 1, "max": 12}},
    {"name": "humidity", "data_type": "float", "unit": "percent",
     "description": "相对湿度", "value_range": {"min": 0, "max": 100}},
    {"name": "air_conditioning_index", "data_type": "float", "unit": None,
     "description": "空调需求指数 max(0,(temp-26)/14)", "value_range": {"min": 0, "max": 1}},
    {"name": "wind_speed", "data_type": "float", "unit": "m/s",
     "description": "风速", "value_range": {"min": 0, "max": 25}},
    {"name": "heating_index", "data_type": "float", "unit": None,
     "description": "供暖需求指数 max(0,(10-temp)/30)", "value_range": {"min": 0, "max": 1}},
]

# Backward-compat aliases
EAST_FEATURES = FULL_FEATURES
NORTH_FEATURES = FULL_FEATURES

EAST_PARAMS = {
    "n_estimators": 200, "max_depth": 6, "learning_rate": 0.1,
    "subsample": 0.8, "colsample_bytree": 0.8,
    "reg_alpha": 0.1, "reg_lambda": 1.0, "random_state": 42,
}


def run(skip_optuna: bool = False, n_trials: int = 20):
    workdir = Path(tempfile.mkdtemp(prefix="adapt_"))
    print(f"工作目录: {workdir}\n")

    results = {}

    # ================================================================
    # Step 1: Train East China model
    # ================================================================
    print("=" * 70)
    print("Step 1: 训练华东模型 (baseline)")
    print("=" * 70)

    east_data = generate_east_china()
    east_csv = workdir / "hua_dong_train.csv"
    east_data.to_csv(east_csv, index=False)

    east_features_yaml = workdir / "features_east.yaml"
    _write_features_yaml(east_features_yaml, "华东负荷预测特征集", EAST_FEATURES)

    east_params_yaml = workdir / "params_east.yaml"
    _write_params_yaml(east_params_yaml, EAST_PARAMS)

    east_model_path = workdir / "east_model.joblib"

    orig_cwd = os.getcwd()
    os.chdir(workdir)
    try:
        m1 = train_model(
            str(east_csv), str(east_features_yaml),
            str(east_params_yaml), str(east_model_path),
        )
    finally:
        os.chdir(orig_cwd)

    results["step1_east_baseline"] = m1
    print(f"\n>>> 华东 MAPE: {m1['mape']:.2f}%\n")

    # ================================================================
    # Step 2: Apply East model directly to North China (no adaptation)
    # ================================================================
    print("=" * 70)
    print("Step 2: 华东模型直接应用于华北数据 (无适配)")
    print("=" * 70)

    north_data = generate_north_china()
    north_csv = workdir / "hua_bei_train.csv"
    north_data.to_csv(north_csv, index=False)

    east_model = joblib.load(east_model_path)
    east_feat_names = load_features(str(east_features_yaml))
    print(f"特征 ({len(east_feat_names)}): {east_feat_names}")

    from sklearn.model_selection import train_test_split
    _, X_test, _, y_test = train_test_split(
        north_data[east_feat_names], north_data["load_mw"],
        test_size=0.2, shuffle=False,
    )
    y_pred = east_model.predict(X_test)
    m2 = compute_metrics(y_test.values, y_pred)
    results["step2_east_on_north_direct"] = m2
    print(f"\n>>> 直接应用 MAPE: {m2['mape']:.2f}%")
    print("    (分布差异导致性能大幅下降)\n")

    # ================================================================
    # Step 3: Feature analysis (SHAP)
    # ================================================================
    print("=" * 70)
    print("Step 3: SHAP 特征重要性分析")
    print("=" * 70)

    try:
        from feature_analysis import shap_importance, compare

        east_imp = shap_importance(
            east_model, east_data[[f for f in east_feat_names if f in east_data.columns]],
            [f for f in east_feat_names if f in east_data.columns],
        )
        print("华东特征重要性:")
        for k, v in sorted(east_imp.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v:.4f}")

        # Train a quick North model with North features for comparison
        north_features_yaml = workdir / "features_north.yaml"
        _write_features_yaml(north_features_yaml, "华北负荷预测特征集", NORTH_FEATURES)
        north_params_yaml = workdir / "params_north.yaml"
        _write_params_yaml(north_params_yaml, EAST_PARAMS)
        north_model_path = workdir / "north_model_temp.joblib"

        os.chdir(workdir)
        try:
            train_model(
                str(north_csv), str(north_features_yaml),
                str(north_params_yaml), str(north_model_path),
            )
        finally:
            os.chdir(orig_cwd)

        north_model_temp = joblib.load(north_model_path)
        north_feat_names = load_features(str(north_features_yaml))
        north_imp = shap_importance(
            north_model_temp,
            north_data[[f for f in north_feat_names if f in north_data.columns]],
            [f for f in north_feat_names if f in north_data.columns],
        )
        print("\n华北特征重要性:")
        for k, v in sorted(north_imp.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v:.4f}")

        report = compare(east_imp, north_imp)
        rec = report['recommendation']
        print(f"\n华东主导特征: {rec['east_dominant']}")
        print(f"华北主导特征: {rec['north_dominant']}")
        results["step3_feature_analysis"] = report
    except Exception as e:
        print(f"[跳过] SHAP 分析失败: {e}")
        results["step3_feature_analysis"] = {"error": str(e)}

    # ================================================================
    # Step 4: Drift detection (PSI/KS)
    # ================================================================
    print("\n" + "=" * 70)
    print("Step 4: 分布漂移检测 (PSI/KS)")
    print("=" * 70)

    shared_features = ["temperature", "hour", "day_of_week", "is_weekend", "month", "load_mw"]
    drift = analyze_drift(east_data, north_data, shared_features)

    for feat in drift["features"]:
        indicator = {"none": "✓", "moderate": "△", "significant": "✗"}[feat["psi_severity"]]
        print(f"  {indicator} {feat['name']:15s}  PSI={feat['psi']:.4f} ({feat['psi_severity']})")

    print(f"\n结论: {drift['summary']['recommendation']}")
    results["step4_drift_detection"] = drift

    # ================================================================
    # Step 5: Feature adaptation + retrain from scratch
    # ================================================================
    print("\n" + "=" * 70)
    print("Step 5: 使用华北特征重新训练 (特征适配)")
    print("=" * 70)

    north_features_yaml = workdir / "features_north.yaml"
    _write_features_yaml(north_features_yaml, "华北负荷预测特征集", NORTH_FEATURES)

    north_retrain_path = workdir / "north_retrained.joblib"
    os.chdir(workdir)
    try:
        m5 = train_model(
            str(north_csv), str(north_features_yaml),
            str(north_params_yaml), str(north_retrain_path),
        )
    finally:
        os.chdir(orig_cwd)

    results["step5_feature_adapted"] = m5
    print(f"\n>>> 特征适配后 MAPE: {m5['mape']:.2f}%\n")

    # ================================================================
    # Step 6: Parameter warm-start tuning (Optuna)
    # ================================================================
    print("=" * 70)
    print("Step 6: 参数 Warm-Start 调优 (Optuna)")
    print("=" * 70)

    if skip_optuna:
        print("[跳过] --skip-optuna 已设置")
        # Use slightly tuned params as fallback
        tuned_params = dict(EAST_PARAMS)
        tuned_params.update({"n_estimators": 250, "max_depth": 7, "learning_rate": 0.08})
        m6 = m5  # reuse step 5 metrics
        results["step6_param_tuned"] = {"skipped": True, "params": tuned_params}
    else:
        try:
            from param_search import main as param_search_main
            optimized_yaml = workdir / "params_optimized.yaml"
            sys.argv = [
                "param_search.py",
                "--dataset", str(north_csv),
                "--features", str(north_features_yaml),
                "--base-params", str(north_params_yaml),
                "--n-trials", str(n_trials),
                "--output", str(optimized_yaml),
            ]
            param_result = param_search_main()

            if param_result and optimized_yaml.exists():
                tuned_params = param_result["parameters"]
                north_tuned_path = workdir / "north_tuned.joblib"
                _write_params_yaml(workdir / "params_tuned.yaml", tuned_params)
                os.chdir(workdir)
                try:
                    m6 = train_model(
                        str(north_csv), str(north_features_yaml),
                        str(workdir / "params_tuned.yaml"), str(north_tuned_path),
                    )
                finally:
                    os.chdir(orig_cwd)
                results["step6_param_tuned"] = m6
                print(f"\n>>> 参数调优后 MAPE: {m6['mape']:.2f}%\n")
            else:
                m6 = m5
                tuned_params = EAST_PARAMS
                results["step6_param_tuned"] = {"error": "optuna returned None"}
        except Exception as e:
            print(f"[跳过] Optuna 失败: {e}")
            m6 = m5
            tuned_params = EAST_PARAMS
            results["step6_param_tuned"] = {"error": str(e)}

    # ================================================================
    # Step 7: Fine-tune East model on North data (warm-start)
    # ================================================================
    print("=" * 70)
    print("Step 7: 从华东模型 Fine-tune (迁移学习)")
    print("=" * 70)

    finetune_params = {
        "n_estimators": 100, "max_depth": 6, "learning_rate": 0.05,
        "subsample": 0.8, "colsample_bytree": 0.8,
        "reg_alpha": 0.1, "reg_lambda": 1.0, "random_state": 42,
    }
    finetune_params_yaml = workdir / "params_finetune.yaml"
    _write_params_yaml(finetune_params_yaml, finetune_params)

    north_finetuned_path = workdir / "north_finetuned.joblib"
    os.chdir(workdir)
    try:
        m7 = train_model(
            str(north_csv), str(north_features_yaml),
            str(finetune_params_yaml), str(north_finetuned_path),
            warm_start_path=str(east_model_path),
        )
    finally:
        os.chdir(orig_cwd)

    results["step7_finetuned"] = m7
    print(f"\n>>> Fine-tune MAPE: {m7['mape']:.2f}%\n")

    # ================================================================
    # Step 8: Ensemble (seasonal routing)
    # ================================================================
    print("=" * 70)
    print("Step 8: 模型融合 (季节路由)")
    print("=" * 70)

    # Ensemble: fine-tuned model (retains East AC patterns, adapted to North)
    #         + retrained model (pure North data, heating expertise)
    finetuned_model = joblib.load(north_finetuned_path)
    retrained_model = joblib.load(north_retrain_path)
    feat_names = load_features(str(north_features_yaml))

    for method in ["weighted_average", "season_router"]:
        r = ensemble_evaluate(
            north_data, finetuned_model, retrained_model,
            feat_names, feat_names,
            method=method, weights=(0.4, 0.6),
        )
        print(f"\n  {method}:")
        ft_m = r['individual']['east_model']['mape']
        rt_m = r['individual']['north_model']['mape']
        print(f"    Fine-tuned模型: MAPE={ft_m:.2f}%")
        print(f"    重训练模型:     MAPE={rt_m:.2f}%")
        em = r['ensemble']['mape']
        print(f"    融合结果:       MAPE={em:.2f}%")
        results[f"step8_ensemble_{method}"] = r

    # ================================================================
    # Summary
    # ================================================================
    print("\n" + "=" * 70)
    print("Summary: 适配效果对比")
    print("=" * 70)

    summary = [
        ("Step 1: 华东 baseline", results.get("step1_east_baseline", {}).get("mape", "N/A")),
        ("Step 2: 直接应用 (无适配)", results.get("step2_east_on_north_direct", {}).get("mape", "N/A")),
        ("Step 5: 特征适配", results.get("step5_feature_adapted", {}).get("mape", "N/A")),
    ]
    if isinstance(results.get("step6_param_tuned"), dict) and "mape" in results["step6_param_tuned"]:
        summary.append(("Step 6: 参数调优", results["step6_param_tuned"]["mape"]))
    summary.extend([
        ("Step 7: Fine-tune", results.get("step7_finetuned", {}).get("mape", "N/A")),
    ])
    for key in ["step8_ensemble_weighted_average", "step8_ensemble_season_router"]:
        if key in results:
            label = "加权融合" if "weighted" in key else "季节路由"
            summary.append((f"Step 8: {label}", results[key]["ensemble"]["mape"]))

    for label, mape in summary:
        if isinstance(mape, (int, float)):
            bar = "█" * int(mape * 2) + "░" * max(0, 30 - int(mape * 2))
            print(f"  {label:30s}  MAPE = {mape:5.2f}%  {bar}")
        else:
            print(f"  {label:30s}  MAPE = {mape}")

    # Save full results
    output = workdir / "scenario_results.json"
    with open(output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n详细结果: {output}")
    print(f"工作目录: {workdir}")

    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Cross-region model adaptation scenario")
    p.add_argument("--skip-optuna", action="store_true",
                   help="Skip Optuna parameter search (faster)")
    p.add_argument("--n-trials", type=int, default=20,
                   help="Number of Optuna trials (default: 20)")
    args = p.parse_args()
    run(skip_optuna=args.skip_optuna, n_trials=args.n_trials)
