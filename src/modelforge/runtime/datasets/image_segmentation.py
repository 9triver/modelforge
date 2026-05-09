"""image-segmentation 数据 loader。

支持 ZIP。约定布局：
  images/
    001.jpg
    002.jpg
  masks/
    001.png    # 与 images 同名，像素值为类别 ID（0=背景）
    002.png

返回 (images, masks)。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from PIL import Image


class DatasetError(ValueError):
    pass


def load_segmentation_dataset(
    path: str | Path,
) -> tuple[list["Image.Image"], list["np.ndarray"]]:
    """读 ZIP/目录，返回 (images, masks)。"""
    raise NotImplementedError("TODO: image segmentation dataset loader")
