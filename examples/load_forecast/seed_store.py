"""
预填充 model_store —— 将 load_forecast 示例的全部资产写入文件存储

用法:
    python examples/load_forecast/seed_store.py          # 独立运行
    python examples/load_forecast/seed_store.py --clean  # 清空后重建

也可通过 seed_all.py 统一调用:
    python examples/seed_all.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

EXAMPLE_DIR = Path(__file__).resolve().parent


class FakeUploadFile:
    """Adaptor so ModelStore.create_version can read a local file."""

    def __init__(self, path: Path):
        self.filename = path.name
        self.file = open(path, "rb")

    def close(self):
        self.file.close()


# ── 特征定义 ──

FEATURES = [
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

TRAINING_PARAMS = {
    "n_estimators": 200,
    "max_depth": 6,
    "learning_rate": 0.1,
    "random_state": 42,
}


def seed(store) -> dict:
    """Seed load_forecast model into an existing store.

    Returns a summary dict with model_id, version_id, slug.
    """
    from modelforge.adapters.filesystem.yaml_io import YAMLFile

    # ── Step 1: Prepare training environment ──
    print("=" * 50)
    print("[负荷预测] Step 1: Preparing training data and config")
    print("=" * 50)

    # 在临时目录中准备训练所需的文件结构
    tmpdir = Path(tempfile.mkdtemp(prefix="modelforge_lf_"))
    try:
        # 写 features.yaml（train_model.py 需要读取）
        feat_dir = tmpdir / "features"
        feat_dir.mkdir()
        import yaml
        with open(feat_dir / "features.yaml", "w") as f:
            yaml.dump({"group_name": "华东负荷预测标准特征集", "features": FEATURES}, f,
                       allow_unicode=True)

        # 写 training_params.yaml
        params_dir = tmpdir / "params"
        params_dir.mkdir()
        with open(params_dir / "training_params.yaml", "w") as f:
            yaml.dump({
                "algorithm": "GradientBoostingRegressor",
                "framework": "sklearn",
                "parameters": TRAINING_PARAMS,
                "train_test_split": {"test_size": 0.2, "shuffle": False},
            }, f, allow_unicode=True)

        # 生成训练数据
        sys.path.insert(0, str(EXAMPLE_DIR))
        from generate_data import generate_load_data
        df = generate_load_data()
        ds_dir = tmpdir / "datasets"
        ds_dir.mkdir()
        train_csv = ds_dir / "train.csv"
        df.to_csv(train_csv, index=False)
        print("  Generated " + str(len(df)) + " rows of training data")

        # 训练模型
        weights_dir = tmpdir / "weights"
        weights_dir.mkdir()
        output_path = str(weights_dir / "load_forecast_model.joblib")

        from train_model import train
        metrics = train(
            dataset_path=str(train_csv),
            feature_config_path=str(feat_dir / "features.yaml"),
            params_path=str(params_dir / "training_params.yaml"),
            output_path=output_path,
        )
        model_file = Path(output_path)
        print("  Model trained, metrics: " + str(metrics))

        # ── Step 2: Register ModelAsset ──
        print("\n" + "=" * 50)
        print("[负荷预测] Step 2: Registering ModelAsset")
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
                "算法假设: 负荷与温度呈非线性关系（U型曲线），"
                "存在明显日周期和周周期。\n"
                "已知局限: 对极端天气事件（台风、暴雪）预测能力有限，"
                "对节假日调休场景需要额外处理。\n"
                "适用条件: 需要至少6个月历史数据，数据采集频率为小时级。"
            ),
            "input_schema": {
                "features": [f["name"] for f in FEATURES],
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
        slug = model.get("slug") or store._find_slug_by_id(model_id)
        print("  Model: " + model["name"] + " (id=" + model_id + ")")

        # ── Step 3: Create ModelVersion with weights ──
        print("\n" + "=" * 50)
        print("[负荷预测] Step 3: Creating ModelVersion 1.0.0")
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
        print("  Version: " + version["version"] + " (id=" + version_id + ")")

        # ── Step 4: Populate artifact directories ──
        print("\n" + "=" * 50)
        print("[负荷预测] Step 4: Populating artifacts")
        print("=" * 50)

        vdir = store._version_dir(slug, "1.0.0")

        # datasets
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

        # code
        for fname in ("train_model.py", "generate_data.py", "requirements.txt"):
            src = EXAMPLE_DIR / fname
            if src.exists():
                shutil.copy(src, vdir / "code" / fname)
        print("  code/      -> train_model.py, generate_data.py, requirements.txt")

        # features
        YAMLFile.write(vdir / "features" / "features.yaml", {
            "group_name": "华东负荷预测标准特征集",
            "features": FEATURES,
        })
        print("  features/  -> features.yaml (6 features)")

        # params
        YAMLFile.write(vdir / "params" / "training_params.yaml", {
            "algorithm": "GradientBoostingRegressor",
            "framework": "sklearn",
            "parameters": TRAINING_PARAMS,
            "train_test_split": {"test_size": 0.2, "shuffle": False},
        })
        YAMLFile.write(vdir / "params" / "recommended_params.yaml", {
            "name": "GBR负荷预测-华东推荐参数",
            "parameters": TRAINING_PARAMS,
            "performance_notes": (
                "在华东2024年全年数据上训练，MAPE约2-3%。\n"
                "建议: 西北地区可能需要增加 n_estimators 到 300。"
            ),
            "regional_adaptations": {
                "华东": "默认参数即可",
                "西北": "建议 n_estimators=300, max_depth=8",
                "华南": "建议增加 humidity 特征权重",
            },
        })
        print("  params/    -> training_params.yaml, recommended_params.yaml")

        # refresh artifact manifest
        store.refresh_artifacts(model_id, version_id)
        print("  artifacts  -> manifest refreshed")

        # ── Step 5: Register global FeatureDefinitions + FeatureGroup ──
        print("\n" + "=" * 50)
        print("[负荷预测] Step 5: Registering FeatureDefinitions & FeatureGroup")
        print("=" * 50)

        feature_ids = []
        for fc in FEATURES:
            f = store.create_feature_definition(fc)
            feature_ids.append(f["id"])
            print("  Feature: " + fc["name"])

        group = store.create_feature_group({
            "name": "华东负荷预测标准特征集",
            "description": "华东地区短期负荷预测标准特征集，包含气象和时间特征",
            "scenario_tags": {"region": "华东", "task": "load_forecast"},
            "feature_ids": feature_ids,
        })
        print("  Group: " + group["name"] + " (" + str(len(feature_ids)) + " features)")

        store.associate_model_group(model_id, group["id"])
        print("  Associated with model")

        # ── Step 6: Register ParameterTemplate ──
        print("\n" + "=" * 50)
        print("[负荷预测] Step 6: Registering ParameterTemplate")
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
            "parameters": TRAINING_PARAMS,
            "performance_notes": (
                "在华东2024年全年数据上训练，MAPE约2-3%。\n"
                "建议: 西北地区可能需要增加 n_estimators 到 300。"
            ),
        })
        print("  Template: " + template["name"])

        # ── Step 7: Save Pipeline definition ──
        print("\n" + "=" * 50)
        print("[负荷预测] Step 7: Saving Pipeline definition")
        print("=" * 50)

        pipeline_yaml = yaml.dump({
            "name": "GBR Load Forecast Training Pipeline",
            "description": "Train GradientBoosting model for short-term load forecast",
            "stages": [
                {
                    "name": "data_prep",
                    "description": "Generate or load hourly load data",
                    "type": "automatic",
                },
                {
                    "name": "training",
                    "description": "Train GBR model with feature & param configs",
                    "type": "automatic",
                    "script": "code/train_model.py",
                    "params_file": "params/training_params.yaml",
                    "features_file": "features/features.yaml",
                },
                {
                    "name": "output",
                    "description": "Evaluate and save model weights",
                    "type": "automatic",
                },
            ],
            "default_params": TRAINING_PARAMS,
        }, allow_unicode=True)
        store.save_pipeline(model_id, pipeline_yaml)
        print("  Pipeline saved (3 stages)")

        # ── Step 8: Transition to shared ──
        print("\n" + "=" * 50)
        print("[负荷预测] Step 8: Transitioning status -> shared")
        print("=" * 50)

        store.transition_status(model_id, "registered")
        print("  draft -> registered")
        store.transition_status(model_id, "shared")
        print("  registered -> shared")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    print("\n[负荷预测] Seed complete!")
    return {"model_id": model_id, "version_id": version_id, "slug": slug}


def main(store_path: Path | None = None, clean: bool = False):
    """Standalone entry point."""
    from modelforge.store import ModelStore

    if store_path is None:
        store_path = PROJECT_ROOT / "model_store"

    if clean and store_path.exists():
        print("  Clearing existing store at " + str(store_path))
        shutil.rmtree(store_path)

    store = ModelStore(store_path)
    print("Store initialized at " + str(store_path) + "\n")
    result = seed(store)
    print("\nModel slug: " + result["slug"])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed model_store with load_forecast example",
    )
    parser.add_argument(
        "--store-path", type=Path, default=None,
        help="Path to model_store directory (default: project_root/model_store)",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Clear existing store before seeding",
    )
    args = parser.parse_args()
    main(args.store_path, args.clean)
