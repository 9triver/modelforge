"""image-segmentation task。

I/O 契约：
  predict(images) -> list[ndarray]
    images: list[PIL.Image.Image]
    返回：每张图的分割 mask，shape (H, W)，dtype int，像素值为类别 ID

model_card.yaml 需声明：
  pipeline_tag: image-segmentation
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .base import TaskHandler, register_task

if TYPE_CHECKING:
    import numpy as np
    from PIL import Image


@register_task
class ImageSegmentationHandler(TaskHandler):
    task = "image-segmentation"

    def predict(self, images: list["Image.Image"]) -> list["np.ndarray"]:
        raise NotImplementedError
