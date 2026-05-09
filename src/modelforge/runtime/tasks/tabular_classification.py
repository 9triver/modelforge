"""tabular-classification task。

I/O 契约：
  predict(df) -> list[Any]
    df: pandas.DataFrame，含特征列（不含 target）
    返回：每行的预测标签列表

model_card.yaml 需声明：
  pipeline_tag: tabular-classification
  tabular:
    target: str           # 目标列名
    features:
      required: [...]
      optional: [...]
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .base import TaskHandler, register_task

if TYPE_CHECKING:
    import pandas as pd


@register_task
class TabularClassificationHandler(TaskHandler):
    task = "tabular-classification"

    def predict(self, df: "pd.DataFrame") -> list[Any]:
        raise NotImplementedError
