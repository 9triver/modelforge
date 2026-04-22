"""生成 cats-vs-dogs 测试 ZIP（ImageFolder 风格）。

从 HuggingFace datasets 拉 'microsoft/cats_vs_dogs' 的 test split 前 N 张，
按 label 分到 cat/ dog/ 子目录，打成 ZIP。

如果 HF datasets 不可用，退回到用 Pillow 生成纯色占位图（能跑通 evaluator
链路但 accuracy 无意义）。

用法：
  pip install datasets Pillow
  python examples/image-classification-demo/make_dataset.py
  python examples/image-classification-demo/make_dataset.py --per-class 20 -o big.zip
"""
from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def _try_hf_datasets(per_class: int, out_dir: Path) -> bool:
    """尝试从 HF datasets 拉真实猫狗图。成功返回 True。"""
    try:
        from datasets import load_dataset
    except ImportError:
        return False

    try:
        ds = load_dataset("microsoft/cats_vs_dogs", split="train", trust_remote_code=True)
    except Exception:
        return False

    counts = {"cat": 0, "dog": 0}
    label_map = {0: "cat", 1: "dog"}

    for item in ds:
        label = label_map.get(item["labels"], None)
        if label is None:
            continue
        if counts[label] >= per_class:
            if all(v >= per_class for v in counts.values()):
                break
            continue
        d = out_dir / label
        d.mkdir(parents=True, exist_ok=True)
        img = item["image"]
        img.save(d / f"{counts[label]}.jpg")
        counts[label] += 1

    return all(v > 0 for v in counts.values())


def _generate_synthetic(per_class: int, out_dir: Path) -> None:
    """生成纯色占位图（fallback）。"""
    from PIL import Image

    for label, color in [("cat", (200, 100, 50)), ("dog", (50, 100, 200))]:
        d = out_dir / label
        d.mkdir(parents=True, exist_ok=True)
        for i in range(per_class):
            c = tuple(max(0, min(255, ch + i * 5)) for ch in color)
            img = Image.new("RGB", (224, 224), color=c)
            img.save(d / f"{i}.jpg")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-class", type=int, default=10, help="每类图片数")
    ap.add_argument("-o", "--output", default="cats_vs_dogs_test.zip")
    args = ap.parse_args()

    tmp = Path("/tmp/mf-catdog-dataset")
    if tmp.exists():
        import shutil
        shutil.rmtree(tmp)
    tmp.mkdir()

    print(f"尝试从 HF datasets 拉 {args.per_class} 张/类...")
    if _try_hf_datasets(args.per_class, tmp):
        print("  OK: 使用真实猫狗图")
    else:
        print("  HF datasets 不可用，生成合成占位图")
        _generate_synthetic(args.per_class, tmp)

    out = Path(args.output)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(tmp.rglob("*")):
            if p.is_file():
                zf.write(p, arcname=str(p.relative_to(tmp.parent)))
    total = sum(1 for _ in tmp.rglob("*.jpg"))
    print(f"wrote {total} images -> {out.resolve()}")


if __name__ == "__main__":
    main()
