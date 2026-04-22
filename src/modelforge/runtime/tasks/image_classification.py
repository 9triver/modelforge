"""image-classification task。

I/O 契约：
  predict(images) -> predictions
    images: list[PIL.Image.Image]
    predictions: list[list[dict]]，每张图一个 list，按 score 降序
      每个元素形如 {"label": "cat", "score": 0.97}

  extract_features(images) -> np.ndarray  # 可选，用于 transfer learning
    images: list[PIL.Image.Image]
    返回 (N, D) float 数组，D = backbone 倒数第二层维度
    不实现的 handler 不能用 Transfer tab 做 linear probe。

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

    def extract_features(self, images: "list[Image]"):
        """Linear probe 等迁移学习用：提取倒数第二层特征向量。

        返回 numpy.ndarray，shape = (len(images), feature_dim)。
        不实现则 Transfer tab 显示"该模型不支持迁移"。
        """
        raise NotImplementedError(
            "该 handler 未实现 extract_features，无法进行迁移学习"
        )
