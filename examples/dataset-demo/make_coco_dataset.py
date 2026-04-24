"""生成合成 COCO 格式数据集并上传到 ModelForge。

生成几张带随机 bbox 的合成图片 + annotations.json，
作为 object-detection dataset 仓库托管。

用法：
  # 仅生成
  python examples/dataset-demo/make_coco_dataset.py

  # 生成并上传
  python examples/dataset-demo/make_coco_dataset.py --upload chun/synthetic-coco

  # 自定义
  python examples/dataset-demo/make_coco_dataset.py --n-images 20 --n-categories 5
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path


CATEGORY_NAMES = [
    "person", "car", "bicycle", "dog", "cat",
    "bus", "truck", "bird", "chair", "bottle",
]


def generate(n_images: int, n_categories: int, seed: int, out_dir: Path) -> dict:
    random.seed(seed)
    from PIL import Image, ImageDraw

    categories = [
        {"id": i + 1, "name": CATEGORY_NAMES[i % len(CATEGORY_NAMES)]}
        for i in range(n_categories)
    ]

    img_dir = out_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    images_meta = []
    annotations = []
    ann_id = 1

    for img_idx in range(n_images):
        w, h = 640, 480
        img = Image.new("RGB", (w, h), color=(
            random.randint(180, 240),
            random.randint(180, 240),
            random.randint(180, 240),
        ))
        draw = ImageDraw.Draw(img)

        n_objs = random.randint(1, 4)
        for _ in range(n_objs):
            cat = random.choice(categories)
            bw = random.randint(40, 200)
            bh = random.randint(40, 200)
            bx = random.randint(0, w - bw)
            by = random.randint(0, h - bh)
            color = (random.randint(50, 200), random.randint(50, 200), random.randint(50, 200))
            draw.rectangle([bx, by, bx + bw, by + bh], fill=color, outline="black", width=2)
            annotations.append({
                "id": ann_id,
                "image_id": img_idx + 1,
                "category_id": cat["id"],
                "bbox": [bx, by, bw, bh],
                "area": bw * bh,
                "iscrowd": 0,
            })
            ann_id += 1

        fname = f"{img_idx:04d}.jpg"
        img.save(img_dir / fname)
        images_meta.append({
            "id": img_idx + 1,
            "file_name": fname,
            "width": w,
            "height": h,
        })

    coco = {
        "images": images_meta,
        "annotations": annotations,
        "categories": categories,
    }
    (out_dir / "annotations.json").write_text(
        json.dumps(coco, indent=2), encoding="utf-8",
    )
    return coco


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-images", type=int, default=10)
    ap.add_argument("--n-categories", type=int, default=3)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("-o", "--output", default="synthetic_coco")
    ap.add_argument("--upload", metavar="REPO", help="上传到 ModelForge")
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--token", default=None)
    args = ap.parse_args()

    out_dir = Path(args.output)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    coco = generate(args.n_images, args.n_categories, args.seed, out_dir)
    n_ann = len(coco["annotations"])
    n_cat = len(coco["categories"])
    print(f"wrote {args.n_images} images, {n_ann} annotations, {n_cat} categories -> {out_dir.resolve()}/")

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

        staging = Path(tempfile.mkdtemp(prefix="mf_ds_coco_"))
        try:
            cat_names = ", ".join(c["name"] for c in coco["categories"])
            readme = (
                "---\n"
                "repo_type: dataset\n"
                "license: mit\n"
                "data_format: coco_json\n"
                "task_categories:\n"
                "  - object-detection\n"
                "tags:\n"
                "  - synthetic\n"
                "  - coco\n"
                "---\n"
                f"# {args.upload}\n\n"
                f"合成 COCO 数据集（{args.n_images} 张图片，{n_ann} 个标注）。\n"
                f"类别：{cat_names}\n"
            )
            (staging / "README.md").write_text(readme, encoding="utf-8")
            shutil.copy2(out_dir / "annotations.json", staging / "annotations.json")
            shutil.copytree(out_dir / "images", staging / "images")

            hub = ModelHub(ep, token=tk)
            sha = hub.upload_folder(
                args.upload, staging,
                f"Upload synthetic COCO dataset ({args.n_images} images, {n_ann} annotations)",
            )
            print(f"uploaded -> {ep}/{args.upload} ({sha[:8]})")
        finally:
            shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    main()
