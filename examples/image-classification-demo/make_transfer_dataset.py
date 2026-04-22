"""生成 CIFAR-10 子集 transfer 数据 ZIP（ImageFolder 风格）。

用 ViT cats-vs-dogs 模型 Transfer → 重新分成 N 类的 CIFAR-10 子集。
验证 linear probe 闭环：预期 accuracy > 0.7（ViT 在低分辨率 CIFAR-10
上的 linear probe 表现）。

CIFAR-10 原图 32x32，我们放大到 224x224 适配 ViT 输入。

用法：
  pip install datasets Pillow
  python examples/image-classification-demo/make_transfer_dataset.py
  python examples/image-classification-demo/make_transfer_dataset.py --classes airplane,automobile,bird --per-class 30 -o transfer.zip
"""
from __future__ import annotations

import argparse
import os
import zipfile
from pathlib import Path

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

CIFAR10_LABELS = [
    "airplane", "automobile", "bird", "cat", "deer",
    "dog", "frog", "horse", "ship", "truck",
]


def _try_hf_datasets(classes: list[str], per_class: int, out_dir: Path) -> bool:
    try:
        from datasets import load_dataset
    except ImportError:
        return False

    try:
        ds = load_dataset("cifar10", split="train")
    except Exception:
        return False

    wanted_idx = {CIFAR10_LABELS.index(c): c for c in classes}
    counts: dict[str, int] = {c: 0 for c in classes}

    for item in ds:
        lbl_idx = item["label"]
        if lbl_idx not in wanted_idx:
            continue
        cls = wanted_idx[lbl_idx]
        if counts[cls] >= per_class:
            if all(v >= per_class for v in counts.values()):
                break
            continue
        d = out_dir / cls
        d.mkdir(parents=True, exist_ok=True)
        # CIFAR-10 原图 32x32，放大到 224x224 适配 ViT
        img = item["img"].convert("RGB").resize((224, 224))
        img.save(d / f"{counts[cls]}.jpg", quality=90)
        counts[cls] += 1

    return all(v > 0 for v in counts.values())


def _generate_synthetic(classes: list[str], per_class: int, out_dir: Path) -> None:
    """HF 拉不到时用纯色占位（能跑通链路，accuracy 可能仍然 OK 因为不同类固定色彩可分）。"""
    from PIL import Image

    palette = [
        (220, 40, 40), (40, 220, 40), (40, 40, 220), (220, 220, 40),
        (220, 40, 220), (40, 220, 220), (180, 100, 50), (50, 180, 100),
        (100, 50, 180), (120, 120, 120),
    ]
    for idx, cls in enumerate(classes):
        color = palette[idx % len(palette)]
        d = out_dir / cls
        d.mkdir(parents=True, exist_ok=True)
        for i in range(per_class):
            c = tuple(max(0, min(255, ch + i * 2)) for ch in color)
            img = Image.new("RGB", (224, 224), color=c)
            img.save(d / f"{i}.jpg", quality=90)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--classes", default="airplane,automobile,bird",
        help=f"逗号分隔，CIFAR-10 类别：{','.join(CIFAR10_LABELS)}",
    )
    ap.add_argument("--per-class", type=int, default=30, help="每类图片数（>=4）")
    ap.add_argument("-o", "--output", default="cifar10_transfer.zip")
    args = ap.parse_args()

    classes = [c.strip() for c in args.classes.split(",") if c.strip()]
    unknown = [c for c in classes if c not in CIFAR10_LABELS]
    if unknown:
        import sys
        sys.exit(f"未知类别: {unknown}。合法：{CIFAR10_LABELS}")
    if len(classes) < 2:
        import sys
        sys.exit("至少选 2 个类别")

    tmp = Path("/tmp/mf-cifar-transfer")
    if tmp.exists():
        import shutil
        shutil.rmtree(tmp)
    tmp.mkdir()

    print(f"尝试从 HF datasets 拉 CIFAR-10，classes={classes}, per_class={args.per_class}")
    if _try_hf_datasets(classes, args.per_class, tmp):
        print("  OK: 使用真实 CIFAR-10 图")
    else:
        print("  HF datasets 不可用，生成合成占位图")
        _generate_synthetic(classes, args.per_class, tmp)

    out = Path(args.output)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(tmp.rglob("*")):
            if p.is_file():
                zf.write(p, arcname=str(p.relative_to(tmp.parent)))
    total = sum(1 for _ in tmp.rglob("*.jpg"))
    print(f"wrote {total} images ({len(classes)} classes) -> {out.resolve()}")


if __name__ == "__main__":
    main()
