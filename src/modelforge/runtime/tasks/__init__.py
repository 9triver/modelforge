"""任务子类与注册表导出。"""
from __future__ import annotations

from .base import TaskHandler, get_task_handler, list_tasks, register_task
from .forecasting import ForecastingHandler
from .image_classification import ImageClassificationHandler
from .object_detection import ObjectDetectionHandler

__all__ = [
    "TaskHandler",
    "ForecastingHandler",
    "ImageClassificationHandler",
    "ObjectDetectionHandler",
    "get_task_handler",
    "list_tasks",
    "register_task",
]
