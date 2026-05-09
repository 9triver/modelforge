"""标准指标实现。按 task 提供默认指标集。"""
from __future__ import annotations

from . import classification, forecasting, regression, segmentation, token_classification

__all__ = [
    "forecasting",
    "classification",
    "regression",
    "token_classification",
    "segmentation",
]
