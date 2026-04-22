"""生成 COCO 格式测试数据 ZIP（用于 object-detection 评估 demo）。

从 COCO val2017 拉前 N 张图 + 对应 annotation，打成 ZIP。
如果 COCO 下载不可用，退回到生成合成数据（带随机 bbox 的纯色图）。

用法：
  python examples/object-detection-demo/make_dataset.py
  python examples/object-detection-demo/make_dataset.py --count 30 -o big.zip
"""
from __future__ import annotations

import argparse
import json
import random
import zipfile
from pathlib import Path


def _generate_synthetic(count: int, out_dir: Path) -> None:
    """生成合成 COCO 数据（fallback）。"""
    from PIL import Image

    images_dir = out_dir / "images"
    images_dir.mkdir(parents=True)

    random.seed(42)
    categories = [
        {"id": 1, "name": "person"},
        {"id": 2, "name": "car"},
        {"id": 3, "name": "dog"},
    ]

    img_entries = []
    ann_entries = []
    ann_id = 1
    for i in range(count):
        w, h = 320, 240
        color = (random.randint(50, 200), random.randint(50, 200), random.randint(50, 200))
        img = Image.new("RGB", (w, h), color=color)
        fname = f"{i:06d}.jpg"
        img.save(images_dir / fname)
        img_entries.append({"id": i + 1, "file_name": fname, "width": w, "height": h})

        n_boxes = random.randint(1, 3)
        for _ in range(n_boxes):
            bx = random.randint(0, w - 50)
            by = random.randint(0, h - 50)
            bw = random.randint(20, min(80, w - bx))
            bh = random.randint(20, min(80, h - by))
            cat = random.choice(categories)
            ann_entries.append({
                "id": ann_id,
                "image_id": i + 1,
                "category_id": cat["id"],
                "bbox": [bx, by, bw, bh],
                "area": bw * bh,
                "iscrowd": 0,
            })
            ann_id += 1

    coco = {
        "images": img_entries,
        "annotations": ann_entries,
        "categories": categories,
    }
    (out_dir / "annotations.json").write_text(json.dumps(coco, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=10, help="图片数")
    ap.add_argument("-o", "--output", default="coco_test.zip")
    args = ap.parse_args()

    tmp = Path("/tmp/mf-coco-dataset")
    if tmp.exists():
        import shutil
        shutil.rmtree(tmp)
    tmp.mkdir()

    print(f"生成 {args.count} 张合成 COCO 数据...")
    _generate_synthetic(args.count, tmp)

    out = Path(args.output)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(tmp.rglob("*")):
            if p.is_file():
                zf.write(p, arcname=str(p.relative_to(tmp.parent)))
    total = sum(1 for _ in (tmp / "images").glob("*.jpg"))
    print(f"wrote {total} images + annotations.json -> {out.resolve()}")


if __name__ == "__main__":
    main()
