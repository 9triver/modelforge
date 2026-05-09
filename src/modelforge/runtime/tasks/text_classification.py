"""text-classification task。

I/O 契约：
  predict(texts) -> list[list[dict]]
    texts: list[str]，原始文本列表
    返回：每条文本的预测列表，每个预测 {"label": str, "score": float}

model_card.yaml 需声明：
  pipeline_tag: text-classification
"""
from __future__ import annotations

from .base import TaskHandler, register_task


@register_task
class TextClassificationHandler(TaskHandler):
    task = "text-classification"

    def predict(self, texts: list[str]) -> list[list[dict]]:
        raise NotImplementedError
