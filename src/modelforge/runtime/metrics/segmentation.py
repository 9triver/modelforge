"""image-segmentation 指标：mIoU / dice / pixel accuracy。

约定输入：
  y_true: list[ndarray]  — 每张图 (H, W) int mask
  y_pred: list[ndarray]  — 同上
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


def compute_all(
    y_true: list["np.ndarray"],
    y_pred: list["np.ndarray"],
) -> dict[str, float | None]:
    """mIoU, dice, pixel_accuracy。"""
    raise NotImplementedError("TODO: segmentation metrics")
