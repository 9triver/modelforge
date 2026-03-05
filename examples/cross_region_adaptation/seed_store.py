"""
预填充 model_store — 华东→华北跨区域适配示例

将完整的跨区域适配场景写入 model_store，包括：
- 华东 XGBoost 负荷预测模型 (v1.0.0, production)
- 华北适配模型 (v1.0.0 直接应用 → v1.1.0 特征适配 → v1.2.0 fine-tune → v1.3.0 融合)
- 全局特征定义 + 特征组
- 参数模板

用法:
    cd examples/cross_region_adaptation
    python seed_store.py
"""

import json
import os
import shutil
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import yaml

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

EXAMPLE_DIR = Path(__file__).resolve().parent
DEFAULT_STORE_PATH = PROJECT_ROOT / "model_store"


class FakeUploadFile:
    """Adaptor so ModelStore.create_version can read a local file."""
    def __init__(self, path: Path):
        self.filename = path.name
        self.file = open(path, "rb")
    def close(self):
        self.file.close()


# Unified 10-feature set (both regions have all features)
ALL_FEATURES = [
    {"name": "temperature", "data_type": "float", "unit": "celsius",
     "description": "环境温度（摄氏度）",
     "value_range": {"min": -40, "max": 50}},
    {"name": "hour", "data_type": "int", "unit": None,
     "description": "一天中的小时 (0-23)",
     "value_range": {"min": 0, "max": 23}},
    {"name": "day_of_week", "data_type": "int", "unit": None,
     "description": "星期几 (0=周一, 6=周日)",
     "value_range": {"min": 0, "max": 6}},
    {"name": "is_weekend", "data_type": "int", "unit": None,
     "description": "是否周末 (0=工作日, 1=周末)",
     "value_range": {"min": 0, "max": 1}},
    {"name": "is_holiday", "data_type": "int", "unit": None,
     "description": "是否法定节假日 (0=否, 1=是)",
     "value_range": {"min": 0, "max": 1}},
    {"name": "month", "data_type": "int", "unit": None,
     "description": "月份 (1-12)",
     "value_range": {"min": 1, "max": 12}},
    {"name": "humidity", "data_type": "float", "unit": "percent",
     "description": "相对湿度，影响体感温度和空调需求",
     "value_range": {"min": 0, "max": 100}},
    {"name": "air_conditioning_index", "data_type": "float",
     "unit": None,
     "description": "空调需求指数 = max(0, (temp-26)/14)",
     "value_range": {"min": 0, "max": 1}},
    {"name": "wind_speed", "data_type": "float", "unit": "m/s",
     "description": "风速，影响风寒效应和供暖需求",
     "value_range": {"min": 0, "max": 25}},
    {"name": "heating_index", "data_type": "float", "unit": None,
     "description": "供暖需求指数 = max(0, (10-temp)/30)",
     "value_range": {"min": 0, "max": 1}},
]

EAST_PARAMS = {
    "n_estimators": 200, "max_depth": 6, "learning_rate": 0.1,
    "subsample": 0.8, "colsample_bytree": 0.8,
    "reg_alpha": 0.1, "reg_lambda": 1.0, "random_state": 42,
}


def _write_yaml(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def main(store_path: Path = DEFAULT_STORE_PATH):
    from modelforge.store import ModelStore, YAMLFile
    from generate_data import generate_east_china, generate_north_china
    from train import train as train_model

    store = ModelStore(store_path)
    print(f"Store: {store_path}\n")

    # ── Generate data ──
    print("=" * 50)
    print("Generating data")
    print("=" * 50)
    east_data = generate_east_china()
    north_data = generate_north_china()
    print(f"  华东: {len(east_data)} rows")
    print(f"  华北: {len(north_data)} rows")

    # Temp files for training
    tmpdir = Path("/tmp/modelforge_seed")
    tmpdir.mkdir(exist_ok=True)
    east_csv = tmpdir / "east.csv"
    north_csv = tmpdir / "north.csv"
    east_data.to_csv(east_csv, index=False)
    north_data.to_csv(north_csv, index=False)

    # Feature YAML files
    east_feat_yaml = tmpdir / "features_east.yaml"
    _write_yaml(east_feat_yaml, {
        "group_name": "华东负荷预测特征集-XGB",
        "target": "load_mw",
        "features": ALL_FEATURES,
    })
    north_feat_yaml = tmpdir / "features_north.yaml"
    _write_yaml(north_feat_yaml, {
        "group_name": "华北负荷预测特征集-XGB",
        "target": "load_mw",
        "features": ALL_FEATURES,
    })

    # Params YAML
    east_params_yaml = tmpdir / "params_east.yaml"
    _write_yaml(east_params_yaml, {
        "algorithm": "XGBRegressor", "framework": "xgboost",
        "parameters": EAST_PARAMS,
        "train_test_split": {"test_size": 0.2, "shuffle": False},
    })

    # ── Train East model ──
    print("\n" + "=" * 50)
    print("Training East China model")
    print("=" * 50)

    east_model_file = tmpdir / "east_model.joblib"
    orig_cwd = os.getcwd()
    os.chdir(tmpdir)
    try:
        east_metrics = train_model(
            str(east_csv), str(east_feat_yaml),
            str(east_params_yaml), str(east_model_file),
        )
    finally:
        os.chdir(orig_cwd)

    # ── Train North model (with north features) ──
    print("\n" + "=" * 50)
    print("Training North China model (feature adapted)")
    print("=" * 50)

    north_model_file = tmpdir / "north_model.joblib"
    os.chdir(tmpdir)
    try:
        north_metrics = train_model(
            str(north_csv), str(north_feat_yaml),
            str(east_params_yaml), str(north_model_file),
        )
    finally:
        os.chdir(orig_cwd)

    # ── Fine-tune from East model ──
    print("\n" + "=" * 50)
    print("Fine-tuning East model on North data")
    print("=" * 50)

    finetune_params_yaml = tmpdir / "params_finetune.yaml"
    _write_yaml(finetune_params_yaml, {
        "algorithm": "XGBRegressor", "framework": "xgboost",
        "parameters": {
            "n_estimators": 100, "max_depth": 6, "learning_rate": 0.05,
            "subsample": 0.8, "colsample_bytree": 0.8,
            "reg_alpha": 0.1, "reg_lambda": 1.0, "random_state": 42,
        },
        "train_test_split": {"test_size": 0.2, "shuffle": False},
    })

    finetuned_model_file = tmpdir / "finetuned_model.joblib"
    os.chdir(tmpdir)
    try:
        ft_metrics = train_model(
            str(north_csv), str(north_feat_yaml),
            str(finetune_params_yaml), str(finetuned_model_file),
            warm_start_path=str(east_model_file),
        )
    finally:
        os.chdir(orig_cwd)

    # ── Register East China model ──
    print("\n" + "=" * 50)
    print("Registering East China model")
    print("=" * 50)

    east_model = store.create_model({
        "name": "华东短期负荷预测-XGBoost",
        "description": "基于XGBoost的华东地区短期负荷预测模型，使用温度、湿度、空调指数等特征",
        "task_type": "load_forecast",
        "algorithm_type": "XGBoost",
        "framework": "xgboost",
        "owner_org": "华东省公司",
        "tags": ["load_forecast", "short_term", "xgboost"],
        "applicable_scenarios": {"region": ["华东"], "season": ["all"]},
    })
    east_model_id = east_model["id"]
    east_slug = east_model.get("slug") or store._find_slug_by_id(east_model_id)
    print(f"  Model: {east_model['name']} (slug={east_slug})")

    # Upload East v1.0.0
    fake = FakeUploadFile(east_model_file)
    try:
        east_v1 = store.create_version(east_model_id, {
            "version": "1.0.0",
            "file_format": "joblib",
            "metrics": east_metrics,
            "description": "华东2024全年数据训练，XGBoost baseline",
        }, fake)
    finally:
        fake.close()
    print(f"  Version: v{east_v1['version']}")

    # Populate East v1.0.0 artifacts
    vdir = store._version_dir(east_slug, "1.0.0")
    shutil.copy(east_csv, vdir / "datasets" / "train.csv")
    YAMLFile.write(vdir / "datasets" / "data.yaml", {
        "name": "华东2024全年负荷数据",
        "source": "synthetic", "records": len(east_data), "frequency": "hourly",
    })
    for fname in ("train.py", "generate_data.py", "feature_analysis.py",
                  "drift_detection.py", "ensemble_predict.py", "requirements.txt"):
        src = EXAMPLE_DIR / fname
        if src.exists():
            shutil.copy(src, vdir / "code" / fname)
    shutil.copy(east_feat_yaml, vdir / "features" / "features.yaml")
    _write_yaml(vdir / "params" / "training_params.yaml", {
        "algorithm": "XGBRegressor", "framework": "xgboost",
        "parameters": EAST_PARAMS,
        "train_test_split": {"test_size": 0.2, "shuffle": False},
    })

    # Pipeline
    YAMLFile.write(store.models_dir / east_slug / "pipeline.yaml", {
        "data_prep": {"dataset": "train.csv", "feature_config": "features.yaml", "target": "load_mw"},
        "training": {"script": "train.py", "params": "training_params.yaml", "requirements": "requirements.txt"},
        "output": {"format": "joblib", "metrics": ["mae", "rmse", "mape"]},
    })

    # Transition East to production
    store.transition_status(east_model_id, "registered")
    store.transition_stage(east_model_id, east_v1["id"], "staging")
    store.transition_stage(east_model_id, east_v1["id"], "production")
    store.transition_status(east_model_id, "shared")
    print("  Status: shared, Version stage: production")

    # ── Register North China model ──
    print("\n" + "=" * 50)
    print("Registering North China model (4 versions)")
    print("=" * 50)

    north_model_asset = store.create_model({
        "name": "华北负荷预测-XGBoost-迁移",
        "description": "从华东模型迁移适配的华北短期负荷预测模型",
        "task_type": "load_forecast",
        "algorithm_type": "XGBoost",
        "framework": "xgboost",
        "owner_org": "华北省公司",
        "tags": ["load_forecast", "short_term", "xgboost", "transfer"],
        "applicable_scenarios": {"region": ["华北"], "season": ["all"]},
    })
    north_model_id = north_model_asset["id"]
    north_slug = north_model_asset.get("slug") or store._find_slug_by_id(north_model_id)
    print(f"  Model: {north_model_asset['name']} (slug={north_slug})")

    # Pipeline for North
    YAMLFile.write(store.models_dir / north_slug / "pipeline.yaml", {
        "data_prep": {"dataset": "train.csv", "feature_config": "features.yaml", "target": "load_mw"},
        "training": {"script": "train.py", "params": "training_params.yaml", "requirements": "requirements.txt"},
        "output": {"format": "joblib", "metrics": ["mae", "rmse", "mape"]},
    })

    # v1.0.0 — East model applied directly (poor performance)
    fake = FakeUploadFile(east_model_file)
    try:
        nv1 = store.create_version(north_model_id, {
            "version": "1.0.0", "file_format": "joblib",
            "metrics": {"mape": 12.0, "mae": 750.0, "rmse": 900.0},
            "description": "华东模型直接应用，未做适配",
            "source_model_id": east_model_id,
        }, fake)
    finally:
        fake.close()
    nv1_dir = store._version_dir(north_slug, "1.0.0")
    shutil.copy(north_csv, nv1_dir / "datasets" / "train.csv")
    shutil.copy(east_feat_yaml, nv1_dir / "features" / "features.yaml")
    _write_yaml(nv1_dir / "params" / "training_params.yaml", {
        "algorithm": "XGBRegressor", "framework": "xgboost",
        "parameters": EAST_PARAMS,
        "train_test_split": {"test_size": 0.2, "shuffle": False},
    })
    print(f"  v1.0.0: 直接应用 (MAPE ~12%)")

    # v1.1.0 — Feature adapted + retrained
    fake = FakeUploadFile(north_model_file)
    try:
        nv2 = store.create_version(north_model_id, {
            "version": "1.1.0", "file_format": "joblib",
            "metrics": north_metrics,
            "description": "使用华北特征集重新训练，参数沿用华东",
            "parent_version_id": nv1["id"],
        }, fake)
    finally:
        fake.close()
    nv2_dir = store._version_dir(north_slug, "1.1.0")
    shutil.copy(north_csv, nv2_dir / "datasets" / "train.csv")
    shutil.copy(north_feat_yaml, nv2_dir / "features" / "features.yaml")
    _write_yaml(nv2_dir / "params" / "training_params.yaml", {
        "algorithm": "XGBRegressor", "framework": "xgboost",
        "parameters": EAST_PARAMS,
        "train_test_split": {"test_size": 0.2, "shuffle": False},
    })
    print(f"  v1.1.0: 特征适配 (MAPE ~{north_metrics.get('mape', 'N/A')}%)")

    # v1.2.0 — Fine-tuned from East
    fake = FakeUploadFile(finetuned_model_file)
    try:
        nv3 = store.create_version(north_model_id, {
            "version": "1.2.0", "file_format": "joblib",
            "metrics": ft_metrics,
            "description": "从华东模型 warm-start fine-tune，学习率0.05，100轮",
            "parent_version_id": nv2["id"],
            "source_model_id": east_model_id,
        }, fake)
    finally:
        fake.close()
    nv3_dir = store._version_dir(north_slug, "1.2.0")
    shutil.copy(north_csv, nv3_dir / "datasets" / "train.csv")
    shutil.copy(north_feat_yaml, nv3_dir / "features" / "features.yaml")
    shutil.copy(east_model_file, nv3_dir / "weights" / "base_model.joblib")
    _write_yaml(nv3_dir / "params" / "training_params.yaml", {
        "algorithm": "XGBRegressor", "framework": "xgboost",
        "parameters": {"n_estimators": 100, "max_depth": 6, "learning_rate": 0.05,
                        "subsample": 0.8, "colsample_bytree": 0.8,
                        "reg_alpha": 0.1, "reg_lambda": 1.0, "random_state": 42},
        "warm_start": {"enabled": True, "base_model": "weights/base_model.joblib"},
        "train_test_split": {"test_size": 0.2, "shuffle": False},
    })
    print(f"  v1.2.0: Fine-tune (MAPE ~{ft_metrics.get('mape', 'N/A')}%)")

    # v1.3.0 — Ensemble placeholder
    fake = FakeUploadFile(finetuned_model_file)
    try:
        nv4 = store.create_version(north_model_id, {
            "version": "1.3.0", "file_format": "joblib",
            "metrics": {"mape": 2.8, "mae": 190.0, "rmse": 230.0},
            "description": "融合模型：华东+华北 fine-tuned，季节路由策略",
            "parent_version_id": nv3["id"],
        }, fake)
    finally:
        fake.close()
    nv4_dir = store._version_dir(north_slug, "1.3.0")
    shutil.copy(north_csv, nv4_dir / "datasets" / "train.csv")
    shutil.copy(north_feat_yaml, nv4_dir / "features" / "features.yaml")
    shutil.copy(east_model_file, nv4_dir / "weights" / "east_model.joblib")
    shutil.copy(finetuned_model_file, nv4_dir / "weights" / "north_model.joblib")
    _write_yaml(nv4_dir / "params" / "ensemble_config.yaml", {
        "strategy": "season_router",
        "members": [
            {"name": "east_model", "weights_file": "east_model.joblib",
             "source": "华东短期负荷预测-XGBoost:v1.0.0", "features": "features_east.yaml"},
            {"name": "north_model", "weights_file": "north_model.joblib",
             "source": "华北负荷预测-XGBoost-迁移:v1.2.0", "features": "features_north.yaml"},
        ],
        "routing": {
            "heating_months": [11, 12, 1, 2, 3],
            "cooling_months": [6, 7, 8, 9],
            "heating_weights": {"east": 0.2, "north": 0.8},
            "cooling_weights": {"east": 0.6, "north": 0.4},
            "default_weights": {"east": 0.5, "north": 0.5},
        },
    })
    print(f"  v1.3.0: 融合 (MAPE ~2.8%)")

    # Copy code to all North versions
    for ver in ["1.0.0", "1.1.0", "1.2.0", "1.3.0"]:
        vd = store._version_dir(north_slug, ver)
        for fname in ("train.py", "generate_data.py", "feature_analysis.py",
                      "drift_detection.py", "ensemble_predict.py", "requirements.txt"):
            src = EXAMPLE_DIR / fname
            if src.exists():
                shutil.copy(src, vd / "code" / fname)

    store.transition_status(north_model_id, "registered")
    print("  Status: registered")

    # ── Register global features ──
    print("\n" + "=" * 50)
    print("Registering global features")
    print("=" * 50)

    feature_ids = {}
    for fc in ALL_FEATURES:
        # Check if already exists
        existing = store.list_feature_definitions(q=fc["name"])
        if existing:
            feature_ids[fc["name"]] = existing[0]["id"]
            print(f"  [exists] {fc['name']}")
        else:
            f = store.create_feature_definition(fc)
            feature_ids[fc["name"]] = f["id"]
            print(f"  [new] {fc['name']}")

    # Both groups use the full 10-feature set
    all_feat_ids = [feature_ids[f["name"]] for f in ALL_FEATURES]

    east_group = store.create_feature_group({
        "name": "华东负荷预测特征集-XGB",
        "description": "华东地区XGBoost特征集，关键：空调指数、湿度",
        "scenario_tags": {
            "region": "华东", "task": "load_forecast",
            "algorithm": "XGBoost",
        },
        "feature_ids": all_feat_ids,
    })
    store.associate_model_group(east_model_id, east_group["id"])
    print(f"  Group: {east_group['name']} ({len(all_feat_ids)})")

    north_group = store.create_feature_group({
        "name": "华北负荷预测特征集-XGB",
        "description": "华北地区XGBoost特征集，关键：供暖指数、温度",
        "scenario_tags": {
            "region": "华北", "task": "load_forecast",
            "algorithm": "XGBoost",
        },
        "feature_ids": all_feat_ids,
    })
    store.associate_model_group(north_model_id, north_group["id"])
    print(f"  Group: {north_group['name']} ({len(all_feat_ids)})")

    # ── Register parameter templates ──
    print("\n" + "=" * 50)
    print("Registering parameter templates")
    print("=" * 50)

    t1 = store.create_parameter_template({
        "name": "XGB负荷预测-华东推荐参数",
        "model_asset_id": east_model_id,
        "algorithm_type": "XGBoost",
        "scenario_tags": {"region": "华东", "climate": "subtropical"},
        "parameters": EAST_PARAMS,
        "performance_notes": f"MAPE ~{east_metrics.get('mape', 'N/A')}%，华东2024全年数据",
    })
    print(f"  Template: {t1['name']}")

    t2 = store.create_parameter_template({
        "name": "XGB负荷预测-华北适配参数",
        "model_asset_id": north_model_id,
        "algorithm_type": "XGBoost",
        "scenario_tags": {"region": "华北", "climate": "continental"},
        "parameters": {"n_estimators": 100, "max_depth": 6, "learning_rate": 0.05,
                        "subsample": 0.8, "colsample_bytree": 0.8,
                        "reg_alpha": 0.1, "reg_lambda": 1.0, "random_state": 42},
        "performance_notes": f"Fine-tune MAPE ~{ft_metrics.get('mape', 'N/A')}%，从华东模型 warm-start",
    })
    print(f"  Template: {t2['name']}")

    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n" + "=" * 50)
    print("Seed complete!")
    print("=" * 50)
    print(f"\nStore: {store_path}")
    print(f"  models/{east_slug}/  (华东, 1 version, production)")
    print(f"  models/{north_slug}/ (华北, 4 versions)")
    print(f"  catalog/features.yaml (10 features, 2 groups)")
    print(f"  catalog/parameter_templates.yaml (2 templates)")
    print(f"\nStart server: make dev")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Seed model_store with cross-region adaptation example")
    p.add_argument("--store-path", type=Path, default=DEFAULT_STORE_PATH)
    args = p.parse_args()
    main(args.store_path)
