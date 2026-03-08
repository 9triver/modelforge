"""
预填充 model_store —— 将 MNIST 手写数字识别示例写入文件存储

用法:
    cd examples/mnist
    python seed_store.py          # 追加到现有 store
    python seed_store.py --clean  # 清空后重建
"""

import json
import shutil
import sys
from pathlib import Path

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


def main(store_path: Path = DEFAULT_STORE_PATH, clean: bool = False):
    from modelforge.store import ModelStore, YAMLFile

    if clean and store_path.exists():
        print("  Clearing existing store at " + str(store_path))
        shutil.rmtree(store_path)

    store = ModelStore(store_path)
    print("Store initialized at " + str(store_path) + "\n")

    # ── Step 1: Ensure model is trained ──
    print("=" * 50)
    print("Step 1: Checking trained model")
    print("=" * 50)

    model_file = EXAMPLE_DIR / "weights" / "mnist_cnn.pt"
    metrics_file = EXAMPLE_DIR / "metrics.json"

    if not model_file.exists():
        print("  Model not found, training...")
        import os
        orig_cwd = os.getcwd()
        os.chdir(EXAMPLE_DIR)
        try:
            from train_model import train
            metrics = train()
        finally:
            os.chdir(orig_cwd)
    else:
        print("  Using existing model: " + str(model_file))
        if metrics_file.exists():
            with open(metrics_file) as f:
                metrics = json.load(f)
        else:
            metrics = {"accuracy": 0.98}

    print("  Accuracy: " + str(metrics.get("accuracy", "unknown")))

    # ── Step 2: Register model asset ──
    print("\n" + "=" * 50)
    print("Step 2: Registering model asset")
    print("=" * 50)

    model = store.create_model({
        "name": "MNIST手写数字识别-CNN",
        "description": (
            "基于卷积神经网络(CNN)的手写数字识别模型。"
            "使用MNIST数据集训练，输入28x28灰度图像，输出0-9数字分类。"
            "可用于电力行业中的手写抄表数据自动识别场景。"
        ),
        "task_type": "digit_recognition",
        "algorithm_type": "CNN",
        "framework": "pytorch",
        "owner_org": "总部AI实验室",
        "tags": ["mnist", "digit_recognition", "cnn", "image_classification"],
        "applicable_scenarios": {
            "region": ["全国"],
            "season": ["all"],
            "equipment_type": ["电表", "仪表"],
        },
        "algorithm_description": (
            "使用 PyTorch 实现的轻量级 CNN: 2层卷积(16/32通道) + 2层全连接(128/10)。\n"
            "适用条件: 28x28 灰度图像输入，单个数字。\n"
            "已知局限: 仅支持单个数字识别，不支持多位数连写。"
        ),
        "input_schema": {
            "format": "image",
            "channels": 1,
            "width": 28,
            "height": 28,
            "normalize": {"mean": 0.1307, "std": 0.3081},
        },
        "output_schema": {
            "type": "classification",
            "classes": 10,
            "labels": ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"],
        },
    })
    model_id = model["id"]
    print("  Model: " + model["name"] + " (id=" + model_id + ")")

    # ── Step 3: Upload version ──
    print("\n" + "=" * 50)
    print("Step 3: Uploading version 1.0.0")
    print("=" * 50)

    fake_file = FakeUploadFile(model_file)
    try:
        version = store.create_version(model_id, {
            "version": "1.0.0",
            "file_format": "torchscript",
            "metrics": metrics,
            "description": "Initial training on MNIST, 3 epochs, accuracy ~98.8%",
        }, fake_file)
    finally:
        fake_file.close()

    version_id = version["id"]
    print("  Version: " + version["version"] + " (id=" + version_id + ")")
    print("  File size: " + str(version["file_size_bytes"]) + " bytes")

    # ── Step 4: Populate version subdirectories ──
    print("\n" + "=" * 50)
    print("Step 4: Populating version assets")
    print("=" * 50)

    slug = model.get("slug") or store._find_slug_by_id(model_id)
    vdir = store._version_dir(slug, "1.0.0")

    # 4a. code
    for fname in ("train_model.py",):
        src = EXAMPLE_DIR / fname
        if src.exists():
            shutil.copy(src, vdir / "code" / fname)
    print("  code/      -> train_model.py")

    # 4b. params
    training_params = {
        "epochs": 3,
        "batch_size": 64,
        "learning_rate": 0.001,
    }
    YAMLFile.write(vdir / "params" / "training_params.yaml", {
        "algorithm": "SimpleCNN",
        "framework": "pytorch",
        "parameters": training_params,
        "optimizer": "Adam",
        "loss_function": "CrossEntropyLoss",
    })
    print("  params/    -> training_params.yaml")

    # 4c. features (image spec)
    YAMLFile.write(vdir / "features" / "features.yaml", {
        "group_name": "MNIST图像特征",
        "modality": "image",
        "input": {
            "channels": 1,
            "width": 28,
            "height": 28,
            "normalize_mean": [0.1307],
            "normalize_std": [0.3081],
        },
        "output": {
            "type": "classification",
            "num_classes": 10,
        },
    })
    print("  features/  -> features.yaml")

    # ── Step 5: Register parameter template ──
    print("\n" + "=" * 50)
    print("Step 5: Registering parameter template")
    print("=" * 50)

    template = store.create_parameter_template({
        "name": "MNIST-CNN推荐参数",
        "model_asset_id": model_id,
        "algorithm_type": "CNN",
        "scenario_tags": {
            "task": "digit_recognition",
            "dataset": "MNIST",
        },
        "parameters": training_params,
        "performance_notes": (
            "3 epochs 即可达到 ~98.8% 准确率。\n"
            "增加到 10 epochs 可达 ~99.2%，但训练时间显著增加。\n"
            "batch_size=64 在 CPU 上训练效率较好。"
        ),
    })
    print("  Template: " + template["name"])

    # ── Step 6: Transition to shared ──
    print("\n" + "=" * 50)
    print("Step 6: Transitioning model to shared")
    print("=" * 50)

    store.transition_status(model_id, "registered")
    print("  draft -> registered")
    store.transition_status(model_id, "shared")
    print("  registered -> shared")

    # ── Step 7: Save pipeline ──
    print("\n" + "=" * 50)
    print("Step 7: Saving pipeline definition")
    print("=" * 50)

    import yaml
    pipeline_yaml = yaml.dump({
        "name": "MNIST CNN Training Pipeline",
        "description": "Train a simple CNN on MNIST digit recognition",
        "stages": [
            {
                "name": "data_prep",
                "description": "Download and prepare MNIST data",
                "type": "automatic",
            },
            {
                "name": "training",
                "description": "Train CNN model",
                "type": "automatic",
                "script": "code/train_model.py",
                "params_file": "params/training_params.yaml",
            },
            {
                "name": "output",
                "description": "Evaluate and save model weights",
                "type": "automatic",
            },
        ],
        "default_params": training_params,
    }, allow_unicode=True)
    store.save_pipeline(model_id, pipeline_yaml)
    print("  Pipeline saved")

    # ── Done ──
    print("\n" + "=" * 50)
    print("Seed complete!")
    print("=" * 50)
    print("\nStore location: " + str(store_path))
    print("Model slug: " + slug)
    print("  model_store/models/" + slug + "/model.yaml")
    print("  model_store/models/" + slug + "/versions/v1.0.0/")
    print("    weights/  code/  features/  params/")
    print("\nStart server with: make dev")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed model_store with MNIST example",
    )
    parser.add_argument(
        "--store-path", type=Path, default=DEFAULT_STORE_PATH,
        help="Path to model_store directory",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Clear existing store before seeding",
    )
    args = parser.parse_args()
    main(args.store_path, args.clean)
