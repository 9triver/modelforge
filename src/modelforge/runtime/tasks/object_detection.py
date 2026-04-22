"""object-detection task。

I/O 契约：
  predict(images) -> predictions
    images: list[PIL.Image.Image]
    predictions: list[list[dict]]，每张图一个 list，按 score 降序
      每个元素形如 {"label": "person", "bbox": [x, y, w, h], "score": 0.95}
      bbox 是 COCO 格式：左上角 (x, y) + 宽高 (w, h)

评估数据格式：ZIP，含 images/ 目录 + annotations.json（COCO format）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import TaskHandler, register_task

if TYPE_CHECKING:
    from PIL.Image import Image


@register_task
class ObjectDetectionHandler(TaskHandler):
    task = "object-detection"

    def predict(self, images: "list[Image]") -> list[list[dict]]:
        raise NotImplementedError
