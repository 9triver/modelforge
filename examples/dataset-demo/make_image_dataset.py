"""生成 ImageFolder 数据集并上传到 ModelForge。

从 HF datasets 拉 CIFAR-10 子集（3 类各 20 张），打成 ImageFolder 目录结构。
作为 dataset 仓库托管后，Transfer tab 可以直接引用。

用法：
  # 仅生成
  python examples/dataset-demo/make_image_dataset.py

  # 生成并上传
  python examples/dataset-demo/make_image_dataset.py --upload chun/cifar10-3class

  # 自定义
  python examples/dataset-demo/make_image_dataset.py --classes airplane,bird,ship --per-class 30
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

DEFAULT_CLASSES = ["airplane", "automobile", "bird"]
CIFAR10_LABELS = [
    "airplane", "automobile", "bird", "cat", "deer",
    "dog", "frog", "horse", "ship", "truck",
]


def _try_hf(classes: list[str], per_class: int, out_dir: Path) -> bool:
    try:
        import os
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        from datasets import load_dataset
    except ImportError:
        return False
    try:
        ds = load_dataset("cifar10", split="train")
    except Exception:
        return False

    counts = {c: 0 for c in classes}
    cls_idx = {CIFAR10_LABELS.index(c): c for c in classes if c in CIFAR10_LABELS}

    for item in ds:
        label = cls_idx.get(item["label"])
        if label is None or counts[label] >= per_class:
            if all(v >= per_class for v in counts.values()):
                break
            continue
        d = out_dir / label
        d.mkdir(parents=True, exist_ok=True)
        item["img"].save(d / f"{counts[label]:03d}.jpg")
        counts[label] += 1

    return all(v > 0 for v in counts.values())


def _generate_synthetic(classes: list[str], per_class: int, out_dir: Path) -> None:
    from PIL import Image
    base_colors = [(200, 50, 50), (50, 200, 50), (50, 50, 200),
                   (200, 200, 50), (200, 50, 200), (50, 200, 200)]
    for i, cls in enumerate(classes):
        d = out_dir / cls
        d.mkdir(parents=True, exist_ok=True)
        color = base_colors[i % len(base_colors)]
        for j in range(per_class):
            c = tuple(max(0, min(255, ch + j * 3)) for ch in color)
            img = Image.new("RGB", (32, 32), color=c)
            img.save(d / f"{j:03d}.jpg")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", default=",".join(DEFAULT_CLASSES),
                    help="逗号分隔的类名（默认 airplane,automobile,bird）")
    ap.add_argument("--per-class", type=int, default=20, help="每类图片数")
    ap.add_argument("-o", "--output", default="cifar10_dataset")
    ap.add_argument("--upload", metavar="REPO", help="上传到 ModelForge")
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--token", default=None)
    args = ap.parse_args()

    classes = [c.strip() for c in args.classes.split(",") if c.strip()]
    out_dir = Path(args.output)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    print(f"生成 {len(classes)} 类 × {args.per_class} 张...")
    if _try_hf(classes, args.per_class, out_dir):
        print("  OK: 使用 CIFAR-10 真实图片")
    else:
        print("  HF datasets 不可用，生成合成占位图")
        _generate_synthetic(classes, args.per_class, out_dir)

    total = sum(1 for _ in out_dir.rglob("*.jpg"))
    print(f"wrote {total} images -> {out_dir.resolve()}/")

    if args.upload:
        import os
        import sys
        import tempfile

        here = Path(__file__).parent
        repo_root = here.parent.parent
        sys.path.insert(0, str(repo_root / "src"))
        from modelforge.client import ModelHub

        ep = args.endpoint or os.environ.get("MODELFORGE_URL", "http://192.168.30.134:8000")
        tk = args.token or os.environ.get("MODELFORGE_TOKEN")
        if not tk:
            sys.exit("请设置 MODELFORGE_TOKEN 环境变量")

        staging = Path(tempfile.mkdtemp(prefix="mf_ds_img_"))
        try:
            readme = (
                "---\n"
                "repo_type: dataset\n"
                "license: mit\n"
                "data_format: image_folder\n"
                "task_categories:\n"
                "  - image-classification\n"
                "tags:\n"
                "  - cifar10\n"
                f"size_category: \"{total}\"\n"
                "---\n"
                f"# {args.upload}\n\n"
                f"CIFAR-10 子集（{len(classes)} 类 × {args.per_class} 张）。\n"
                f"类别：{', '.join(classes)}\n"
            )
            (staging / "README.md").write_text(readme, encoding="utf-8")
            for child in out_dir.iterdir():
                if child.is_dir():
                    shutil.copytree(child, staging / child.name)
                else:
                    shutil.copy2(child, staging / child.name)

            hub = ModelHub(ep, token=tk)
            sha = hub.upload_folder(
                args.upload, staging,
                f"Upload CIFAR-10 subset ({len(classes)} classes, {total} images)",
            )
            print(f"uploaded -> {ep}/{args.upload} ({sha[:8]})")
        finally:
            shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    main()
