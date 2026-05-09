"""token-classification（NER）span-level 指标。

约定 span 格式：[{"entity": str, "start": int, "end": int}, ...]
匹配规则：entity 类型 + start + end 完全一致算 TP。
"""
from __future__ import annotations

from typing import Any


def compute_all(
    y_true: list[list[dict[str, Any]]],
    y_pred: list[list[dict[str, Any]]],
) -> dict[str, float | None]:
    """Span-level precision / recall / F1。"""
    raise NotImplementedError("TODO: token classification metrics")
