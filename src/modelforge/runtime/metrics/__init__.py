"""标准指标实现。按 task 提供默认指标集。"""
from __future__ import annotations

from . import classification, forecasting

__all__ = ["forecasting", "classification"]
