"""token-classification task（NER / 序列标注）。

I/O 契约：
  predict(texts) -> list[list[dict]]
    texts: list[str]，原始文本列表
    返回：每条文本的实体列表，每个实体
          {"word": str, "entity": str, "start": int, "end": int, "score": float}

model_card.yaml 需声明：
  pipeline_tag: token-classification
"""
from __future__ import annotations

from .base import TaskHandler, register_task


@register_task
class TokenClassificationHandler(TaskHandler):
    task = "token-classification"

    def predict(self, texts: list[str]) -> list[list[dict]]:
        raise NotImplementedError
