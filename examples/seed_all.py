"""
一键初始化 model_store —— 清空并重建所有示例模型资源

创建的实体:
  - 负荷预测: ModelAsset + ModelVersion + 6 FeatureDefinitions
                + FeatureGroup + ParameterTemplate + Pipeline
  - MNIST:    ModelAsset + ModelVersion + ParameterTemplate + Pipeline

用法:
    python examples/seed_all.py              # 清空并重建
    python examples/seed_all.py --keep       # 保留现有数据
    python examples/seed_all.py --store-path /tmp/store
"""

import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "examples" / "load_forecast"))
sys.path.insert(0, str(PROJECT_ROOT / "examples" / "mnist"))


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Seed model_store with all examples",
    )
    parser.add_argument(
        "--store-path", type=Path, default=None,
        help="Path to model_store (default: project_root/model_store)",
    )
    parser.add_argument(
        "--keep", action="store_true",
        help="Keep existing store (default: clear first)",
    )
    args = parser.parse_args()

    store_path = args.store_path
    if store_path is None:
        store_path = PROJECT_ROOT / "model_store"

    # ── Clear store ──
    if not args.keep and store_path.exists():
        print("Clearing existing store: " + str(store_path))
        shutil.rmtree(store_path)
        print()

    from modelforge.store import ModelStore
    store = ModelStore(store_path)
    print("Store initialized: " + str(store_path))
    print()

    results = {}

    # ── 1. Load Forecast ──
    print("=" * 60)
    print("  SEEDING: 负荷预测模型 (load_forecast)")
    print("=" * 60 + "\n")

    from load_forecast.seed_store import seed as seed_lf
    results["load_forecast"] = seed_lf(store)

    print()

    # ── 2. MNIST ──
    print("=" * 60)
    print("  SEEDING: MNIST 手写数字识别模型")
    print("=" * 60 + "\n")

    from mnist.seed_store import seed as seed_mnist
    results["mnist"] = seed_mnist(store)

    # ── Summary ──
    print("\n" + "=" * 60)
    print("  ALL SEEDS COMPLETE")
    print("=" * 60)
    print()
    print("Store: " + str(store_path))
    print()
    for name, info in results.items():
        print("  " + name + ":")
        print("    slug = " + info["slug"])
        print("    model_id = " + info["model_id"])
        print("    version_id = " + info["version_id"])
    print()
    print("Start server: make dev")
    print("Or: uvicorn modelforge.main:app --reload")


if __name__ == "__main__":
    main()
