"""time-series-forecasting 默认指标。

所有函数接受 iterable[float]（真实值、预测值），返回标量。
纯 Python 实现，无 numpy 依赖——保持 runtime 轻量。
"""
from __future__ import annotations

import math
from collections.abc import Iterable


def _pair(y_true: Iterable[float], y_pred: Iterable[float]) -> list[tuple[float, float]]:
    pairs = list(zip(y_true, y_pred, strict=True))
    if not pairs:
        raise ValueError("y_true / y_pred 不能为空")
    return pairs


def mae(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    pairs = _pair(y_true, y_pred)
    return sum(abs(a - b) for a, b in pairs) / len(pairs)


def rmse(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    pairs = _pair(y_true, y_pred)
    return math.sqrt(sum((a - b) ** 2 for a, b in pairs) / len(pairs))


def mape(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Mean Absolute Percentage Error，返回 0-1 之间的小数（不是百分数）。

    真实值为 0 的点会被跳过，全零时抛 ValueError。
    """
    pairs = _pair(y_true, y_pred)
    vals = [abs((a - b) / a) for a, b in pairs if a != 0]
    if not vals:
        raise ValueError("mape: 所有真实值都是 0，无法计算")
    return sum(vals) / len(vals)


def smape(y_true: Iterable[float], y_pred: Iterable[float]) -> float:
    """Symmetric MAPE，定义：mean( 2 * |y-ŷ| / (|y|+|ŷ|) )，返回 0-2 之间的值。"""
    pairs = _pair(y_true, y_pred)
    vals = []
    for a, b in pairs:
        denom = abs(a) + abs(b)
        if denom == 0:
            continue
        vals.append(2 * abs(a - b) / denom)
    if not vals:
        raise ValueError("smape: 所有 (|y|+|ŷ|) 都是 0，无法计算")
    return sum(vals) / len(vals)


FORECASTING_METRICS = {
    "mae": mae,
    "rmse": rmse,
    "mape": mape,
    "smape": smape,
}


def compute_all(y_true: Iterable[float], y_pred: Iterable[float]) -> dict[str, float]:
    """一次算出所有默认指标。任一指标失败时该键值为 None。"""
    y_true = list(y_true)
    y_pred = list(y_pred)
    out: dict[str, float | None] = {}
    for name, fn in FORECASTING_METRICS.items():
        try:
            out[name] = fn(y_true, y_pred)
        except ValueError:
            out[name] = None
    return out
