"""任务子类与注册表导出。"""
from __future__ import annotations

from .base import TaskHandler, get_task_handler, list_tasks, register_task
from .forecasting import ForecastingHandler
from .image_classification import ImageClassificationHandler

__all__ = [
    "TaskHandler",
    "ForecastingHandler",
    "ImageClassificationHandler",
    "get_task_handler",
    "list_tasks",
    "register_task",
]
