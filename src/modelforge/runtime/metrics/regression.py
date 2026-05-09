"""tabular-regression 默认指标。

纯 Python 实现，无 numpy 依赖。
"""
from __future__ import annotations

import math
from collections.abc import Iterable


def _pair(y_true: Iterable[float], y_pred: Iterable[float]) -> list[tuple[float, float]]:
    pairs = list(zip(y_true, y_pred, strict=True))
    if not pairs:
        raise ValueError("y_true / y_pred 不能为空")
    return pairs


def mse(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    pairs = _pair(y_true, y_pred)
    return sum((a - b) ** 2 for a, b in pairs) / len(pairs)


def mae(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    pairs = _pair(y_true, y_pred)
    return sum(abs(a - b) for a, b in pairs) / len(pairs)


def rmse(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    return math.sqrt(mse(y_true, y_pred))


def r2(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    pairs = _pair(y_true, y_pred)
    mean_y = sum(a for a, _ in pairs) / len(pairs)
    ss_res = sum((a - b) ** 2 for a, b in pairs)
    ss_tot = sum((a - mean_y) ** 2 for a, _ in pairs)
    if ss_tot == 0:
        return 0.0
    return 1.0 - ss_res / ss_tot


REGRESSION_METRICS = {
    "mse": mse,
    "mae": mae,
    "rmse": rmse,
    "r2": r2,
}


def compute_all(y_true: Iterable[float], y_pred: Iterable[float]) -> dict[str, float | None]:
    y_true = list(y_true)
    y_pred = list(y_pred)
    out: dict[str, float | None] = {}
    for name, fn in REGRESSION_METRICS.items():
        try:
            out[name] = fn(y_true, y_pred)
        except ValueError:
            out[name] = None
    return out
