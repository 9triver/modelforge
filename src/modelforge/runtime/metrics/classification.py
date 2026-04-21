"""classification 默认指标（image-classification / text-classification 通用）。

约定：标签用字符串或整数均可，内部统一转 str 比较。
precision / recall / f1 默认 macro 平均。
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from typing import Any


def _pair(y_true: Iterable[Any], y_pred: Iterable[Any]) -> list[tuple[str, str]]:
    pairs = [(str(a), str(b)) for a, b in zip(y_true, y_pred, strict=True)]
    if not pairs:
        raise ValueError("y_true / y_pred 不能为空")
    return pairs


def accuracy(y_true: Iterable[Any], y_pred: Iterable[Any]) -> float:
    pairs = _pair(y_true, y_pred)
    return sum(1 for a, b in pairs if a == b) / len(pairs)


def _per_class_counts(pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """返回 {label: {tp, fp, fn}}。"""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    labels = {a for a, _ in pairs} | {b for _, b in pairs}
    for label in labels:
        counts[label]  # 触发 defaultdict 初始化
    for true, pred in pairs:
        if true == pred:
            counts[true]["tp"] += 1
        else:
            counts[pred]["fp"] += 1
            counts[true]["fn"] += 1
    return counts


def precision_macro(y_true: Iterable[Any], y_pred: Iterable[Any]) -> float:
    counts = _per_class_counts(_pair(y_true, y_pred))
    vals = []
    for c in counts.values():
        denom = c["tp"] + c["fp"]
        vals.append(c["tp"] / denom if denom else 0.0)
    return sum(vals) / len(vals) if vals else 0.0


def recall_macro(y_true: Iterable[Any], y_pred: Iterable[Any]) -> float:
    counts = _per_class_counts(_pair(y_true, y_pred))
    vals = []
    for c in counts.values():
        denom = c["tp"] + c["fn"]
        vals.append(c["tp"] / denom if denom else 0.0)
    return sum(vals) / len(vals) if vals else 0.0


def f1_macro(y_true: Iterable[Any], y_pred: Iterable[Any]) -> float:
    counts = _per_class_counts(_pair(y_true, y_pred))
    vals = []
    for c in counts.values():
        p_denom = c["tp"] + c["fp"]
        r_denom = c["tp"] + c["fn"]
        p = c["tp"] / p_denom if p_denom else 0.0
        r = c["tp"] / r_denom if r_denom else 0.0
        vals.append(2 * p * r / (p + r) if (p + r) else 0.0)
    return sum(vals) / len(vals) if vals else 0.0


CLASSIFICATION_METRICS = {
    "accuracy": accuracy,
    "precision_macro": precision_macro,
    "recall_macro": recall_macro,
    "f1_macro": f1_macro,
}


def compute_all(y_true: Iterable[Any], y_pred: Iterable[Any]) -> dict[str, float]:
    y_true = list(y_true)
    y_pred = list(y_pred)
    return {name: fn(y_true, y_pred) for name, fn in CLASSIFICATION_METRICS.items()}
