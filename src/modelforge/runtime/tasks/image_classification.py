"""image-classification task。

I/O 契约：
  predict(images) -> predictions
    images: list[PIL.Image.Image]
    predictions: list[list[dict]]，每张图一个 list，按 score 降序
      每个元素形如 {"label": "cat", "score": 0.97}

评估数据格式：ZIP，ImageFolder 风格（class_name/xxx.jpg）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import TaskHandler, register_task

if TYPE_CHECKING:
    from PIL.Image import Image


@register_task
class ImageClassificationHandler(TaskHandler):
    task = "image-classification"

    def predict(self, images: "list[Image]") -> list[list[dict]]:
        raise NotImplementedError
