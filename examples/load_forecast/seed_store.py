"""
预填充 model_store —— 将 load_forecast 示例的全部资产写入文件存储

用法:
    cd examples/load_forecast
    python seed_store.py
"""

import shutil
import sys
from pathlib import Path

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


def main(store_path: Path = DEFAULT_STORE_PATH):
    # ── lazy imports (need sys.path set first) ──
    from modelforge.store import ModelStore, YAMLFile

    if store_path.exists():
        print(f"  Clearing existing store at {store_path}")
        shutil.rmtree(store_path)

    store = ModelStore(store_path)
    print(f"Store initialized at {store_path}\n")

    # ── Step 1: Train model ──
    print("=" * 50)
    print("Step 1: Training model")
    print("=" * 50)

    # train_model.py writes to cwd, so chdir temporarily
    import os

    orig_cwd = os.getcwd()
    os.chdir(EXAMPLE_DIR)
    try:
        from train_model import train

        metrics = train()
    finally:
        os.chdir(orig_cwd)

    model_file = EXAMPLE_DIR / "load_forecast_model.joblib"
    assert model_file.exists(), f"Training did not produce {model_file}"

    # ── Step 2: Generate training data ──
    print("\n" + "=" * 50)
    print("Step 2: Generating training data")
    print("=" * 50)

    from generate_data import generate_load_data

    df = generate_load_data()
    train_csv = EXAMPLE_DIR / "train_data.csv"
    df.to_csv(train_csv, index=False)
    print(f"  Generated {len(df)} rows -> {train_csv.name}")

    # ── Step 3: Register model asset ──
    print("\n" + "=" * 50)
    print("Step 3: Registering model asset")
    print("=" * 50)

    model = store.create_model({
        "name": "华东短期负荷预测模型-GBR-v1",
        "description": (
            "基于梯度提升回归(GradientBoosting)的短期电力负荷预测模型。"
            "使用温度、湿度、时间特征预测未来24小时负荷。"
            "在华东地区2024年全年数据上训练，适用于温带气候区域。"
        ),
        "task_type": "load_forecast",
        "algorithm_type": "GradientBoosting",
        "framework": "sklearn",
        "owner_org": "华东省公司",
        "tags": ["load_forecast", "short_term", "gradient_boosting", "tabular"],
        "applicable_scenarios": {
            "region": ["华东", "华中", "华南"],
            "season": ["all"],
            "forecast_horizon": "24h",
            "data_frequency": "hourly",
        },
        "algorithm_description": (
            "使用 sklearn GradientBoostingRegressor 集成学习算法。\n"
            "算法假设: 负荷与温度呈非线性关系（U型曲线），存在明显日周期和周周期。\n"
            "已知局限: 对极端天气事件（台风、暴雪）预测能力有限，"
            "对节假日调休场景需要额外处理。\n"
            "适用条件: 需要至少6个月历史数据，数据采集频率为小时级。"
        ),
        "input_schema": {
            "features": [
                "temperature", "humidity", "hour", "day_of_week", "is_weekend", "month",
            ],
            "types": {
                "temperature": "float (celsius)",
                "humidity": "float (percent)",
                "hour": "int (0-23)",
                "day_of_week": "int (0=Mon, 6=Sun)",
                "is_weekend": "int (0 or 1)",
                "month": "int (1-12)",
            },
        },
        "output_schema": {"load_mw": "float (megawatts)"},
    })
    model_id = model["id"]
    print(f"  Model: {model['name']} (id={model_id})")

    # ── Step 4: Upload version ──
    print("\n" + "=" * 50)
    print("Step 4: Uploading version 1.0.0")
    print("=" * 50)

    fake_file = FakeUploadFile(model_file)
    try:
        version = store.create_version(model_id, {
            "version": "1.0.0",
            "file_format": "joblib",
            "metrics": metrics,
            "description": "Initial training on 2024 华东 full-year data",
        }, fake_file)
    finally:
        fake_file.close()

    version_id = version["id"]
    print(f"  Version: {version['version']} (id={version_id})")
    print(f"  File size: {version['file_size_bytes']} bytes")

    # ── Step 5: Populate version subdirectories ──
    print("\n" + "=" * 50)
    print("Step 5: Populating version assets")
    print("=" * 50)

    slug = model.get("slug")
    if not slug:
        slug = store._find_slug_by_id(model_id)
    vdir = store._version_dir(slug, "1.0.0")

    # 5a. datasets
    shutil.copy(train_csv, vdir / "datasets" / "train.csv")
    YAMLFile.write(vdir / "datasets" / "data.yaml", {
        "name": "华东2024全年负荷数据",
        "description": "合成的华东地区2024年逐时负荷数据，包含气象和时间特征",
        "source": "synthetic (generate_data.py)",
        "records": len(df),
        "time_range": {"start": "2024-01-01", "end": "2024-12-31"},
        "frequency": "hourly",
        "columns": {
            "temperature": "环境温度 (°C)",
            "humidity": "相对湿度 (%)",
            "hour": "小时 (0-23)",
            "day_of_week": "星期 (0=周一, 6=周日)",
            "is_weekend": "是否周末 (0/1)",
            "month": "月份 (1-12)",
            "load_mw": "负荷 (MW) - 预测目标",
        },
    })
    print("  datasets/  -> train.csv + data.yaml")

    # 5b. code
    for fname in ("train_model.py", "generate_data.py", "requirements.txt"):
        src = EXAMPLE_DIR / fname
        if src.exists():
            shutil.copy(src, vdir / "code" / fname)
    print("  code/      -> train_model.py, generate_data.py, requirements.txt")

    # 5c. features snapshot
    features_config = [
        {
            "name": "temperature", "data_type": "float", "unit": "celsius",
            "description": "环境温度（摄氏度）", "value_range": {"min": -40, "max": 50},
        },
        {
            "name": "humidity", "data_type": "float", "unit": "percent",
            "description": "相对湿度（百分比）", "value_range": {"min": 0, "max": 100},
        },
        {
            "name": "hour", "data_type": "int", "unit": None,
            "description": "一天中的小时 (0-23)", "value_range": {"min": 0, "max": 23},
        },
        {
            "name": "day_of_week", "data_type": "int", "unit": None,
            "description": "星期几 (0=周一, 6=周日)", "value_range": {"min": 0, "max": 6},
        },
        {
            "name": "is_weekend", "data_type": "int", "unit": None,
            "description": "是否周末 (0=工作日, 1=周末)", "value_range": {"min": 0, "max": 1},
        },
        {
            "name": "month", "data_type": "int", "unit": None,
            "description": "月份 (1-12)", "value_range": {"min": 1, "max": 12},
        },
    ]
    YAMLFile.write(vdir / "features" / "features.yaml", {
        "group_name": "华东负荷预测标准特征集",
        "features": features_config,
    })
    print("  features/  -> features.yaml (6 features)")

    # 5d. params
    training_params = {
        "n_estimators": 200,
        "max_depth": 6,
        "learning_rate": 0.1,
        "random_state": 42,
    }
    YAMLFile.write(vdir / "params" / "training_params.yaml", {
        "algorithm": "GradientBoostingRegressor",
        "framework": "sklearn",
        "parameters": training_params,
        "train_test_split": {"test_size": 0.2, "shuffle": False},
    })
    YAMLFile.write(vdir / "params" / "recommended_params.yaml", {
        "name": "GBR负荷预测-华东推荐参数",
        "parameters": training_params,
        "performance_notes": (
            "在华东2024年全年数据上训练，MAPE约2-3%。\n"
            "建议: 西北地区可能需要增加 n_estimators 到 300，因为气温变化更剧烈。"
        ),
        "regional_adaptations": {
            "华东": "默认参数即可",
            "西北": "建议 n_estimators=300, max_depth=8",
            "华南": "建议增加 humidity 特征权重",
        },
    })
    print("  params/    -> training_params.yaml, recommended_params.yaml")

    # ── Step 6: Register global features ──
    print("\n" + "=" * 50)
    print("Step 6: Registering global features")
    print("=" * 50)

    feature_ids = []
    for fc in features_config:
        f = store.create_feature_definition(fc)
        feature_ids.append(f["id"])
        print(f"  Feature: {fc['name']}")

    group = store.create_feature_group({
        "name": "华东负荷预测标准特征集",
        "description": "华东地区短期负荷预测标准特征集，包含气象和时间特征",
        "scenario_tags": {"region": "华东", "task": "load_forecast"},
        "feature_ids": feature_ids,
    })
    print(f"  Group: {group['name']} ({len(group['features'])} features)")

    store.associate_model_group(model_id, group["id"])
    print(f"  Associated with model")

    # ── Step 7: Register parameter template ──
    print("\n" + "=" * 50)
    print("Step 7: Registering parameter template")
    print("=" * 50)

    template = store.create_parameter_template({
        "name": "GBR负荷预测-华东推荐参数",
        "model_asset_id": model_id,
        "algorithm_type": "GradientBoosting",
        "scenario_tags": {
            "region": "华东",
            "forecast_horizon": "24h",
            "climate": "temperate",
        },
        "parameters": training_params,
        "performance_notes": (
            "在华东2024年全年数据上训练，MAPE约2-3%。\n"
            "建议: 西北地区可能需要增加 n_estimators 到 300，因为气温变化更剧烈。"
        ),
    })
    print(f"  Template: {template['name']}")

    # ── Step 8: Transition to shared ──
    print("\n" + "=" * 50)
    print("Step 8: Transitioning model to shared")
    print("=" * 50)

    store.transition_status(model_id, "registered")
    print("  draft -> registered")
    store.transition_status(model_id, "shared")
    print("  registered -> shared")

    # ── Cleanup temp files ──
    train_csv.unlink(missing_ok=True)

    # ── Done ──
    print("\n" + "=" * 50)
    print("Seed complete!")
    print("=" * 50)
    print(f"\nStore location: {store_path}")
    print(f"Model slug: {slug}")
    print(f"  model_store/models/{slug}/model.yaml")
    print(f"  model_store/models/{slug}/versions/v1.0.0/")
    print(f"    weights/  datasets/  code/  features/  params/")
    print(f"  model_store/catalog/features.yaml")
    print(f"  model_store/catalog/parameter_templates.yaml")
    print(f"\nStart server with: make dev")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed model_store with load_forecast example")
    parser.add_argument(
        "--store-path", type=Path, default=DEFAULT_STORE_PATH,
        help="Path to model_store directory (default: project_root/model_store)",
    )
    args = parser.parse_args()
    main(args.store_path)
