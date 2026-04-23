"""image-classification task。

I/O 契约：
  predict(images) -> predictions
    images: list[PIL.Image.Image]
    predictions: list[list[dict]]，每张图一个 list，按 score 降序
      每个元素形如 {"label": "cat", "score": 0.97}

  extract_features(images) -> np.ndarray  # 可选，用于 linear probe
    images: list[PIL.Image.Image]
    返回 (N, D) float 数组，D = backbone 倒数第二层维度

  fine_tune(images, labels, ...) -> dict  # 可选，用于 fine-tune transfer
    训练后返回 {"weights_path": ..., "config": ..., "classes": [...]}

评估数据格式：ZIP，ImageFolder 风格（class_name/xxx.jpg）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from .base import TaskHandler, register_task

if TYPE_CHECKING:
    from PIL.Image import Image


@register_task
class ImageClassificationHandler(TaskHandler):
    task = "image-classification"

    def predict(self, images: "list[Image]") -> list[list[dict]]:
        raise NotImplementedError

    def extract_features(self, images: "list[Image]"):
        """Linear probe 用：提取倒数第二层特征向量。

        返回 numpy.ndarray，shape = (len(images), feature_dim)。
        """
        raise NotImplementedError(
            "该 handler 未实现 extract_features，无法进行迁移学习"
        )

    def fine_tune(
        self,
        images: "list[Image]",
        labels: list[str],
        *,
        method: str = "full",
        epochs: int = 10,
        lr: float = 1e-5,
        unfreeze_layers: int = 2,
        progress_cb: Callable[[int, int, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Fine-tune 最后几层或 LoRA adapter。

        Args:
            method: "full"（解冻最后 N 层）或 "lora"（LoRA adapter）
            epochs: 训练轮数
            lr: 学习率
            unfreeze_layers: full 模式下解冻的层数
            progress_cb: (current_epoch, total_epochs, metrics) 回调

        Returns:
            {"weights_path": str, "config": dict, "classes": list[str]}
        """
        raise NotImplementedError(
            "该 handler 未实现 fine_tune，无法进行 fine-tune 迁移"
        )
