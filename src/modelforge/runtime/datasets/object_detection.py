"""object-detection 标准评估数据 loader（COCO JSON 格式）。

数据目录结构：
  root/
    images/
      000001.jpg
      ...
    annotations.json    # COCO format

annotations.json 遵循 COCO 标准：
  {
    "images": [{"id": 1, "file_name": "000001.jpg", "width": 640, "height": 480}],
    "annotations": [{"id": 1, "image_id": 1, "category_id": 1,
                     "bbox": [x,y,w,h], "area": ..., "iscrowd": 0}],
    "categories": [{"id": 1, "name": "person"}, ...]
  }

依赖 Pillow（来自 runtime-vision extras）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .image_classification import DatasetError, unpack_zip

if TYPE_CHECKING:
    from PIL.Image import Image

__all__ = ["unpack_zip", "load_coco_dataset", "DatasetError"]


def load_coco_dataset(
    root: str | Path,
) -> tuple[list["Image"], list[int], dict[str, Any]]:
    """加载 COCO 格式数据集。

    Returns:
        (images, image_ids, coco_dict)
        - images: PIL Image 列表，按 coco_dict["images"] 顺序
        - image_ids: 对应的 image id 列表
        - coco_dict: 原始 COCO annotation dict（给 pycocotools 用）
    """
    from PIL import Image as PILImage

    root_p = Path(root)

    ann_path = root_p / "annotations.json"
    if not ann_path.is_file():
        raise DatasetError(f"缺少 annotations.json：{ann_path}")

    try:
        coco_dict = json.loads(ann_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise DatasetError(f"annotations.json 解析失败：{e}")

    if "images" not in coco_dict or "annotations" not in coco_dict:
        raise DatasetError("annotations.json 缺少 'images' 或 'annotations' 字段")

    images_dir = root_p / "images"
    if not images_dir.is_dir():
        images_dir = root_p

    images: list[Image] = []
    image_ids: list[int] = []
    for img_info in coco_dict["images"]:
        img_id = img_info["id"]
        fname = img_info["file_name"]
        img_path = images_dir / fname
        if not img_path.is_file():
            raise DatasetError(f"图片不存在：{img_path}（image_id={img_id}）")
        try:
            img = PILImage.open(img_path).convert("RGB")
        except Exception as e:
            raise DatasetError(f"无法读取图片 {img_path}：{e}")
        images.append(img)
        image_ids.append(img_id)

    if not images:
        raise DatasetError(f"{root_p} 下没有找到任何图片")

    return images, image_ids, coco_dict
