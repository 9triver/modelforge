"""任务子类与注册表导出。"""
from __future__ import annotations

from .base import TaskHandler, get_task_handler, list_tasks, register_task
from .forecasting import ForecastingHandler
from .image_classification import ImageClassificationHandler
from .image_segmentation import ImageSegmentationHandler
from .object_detection import ObjectDetectionHandler
from .tabular_classification import TabularClassificationHandler
from .tabular_regression import TabularRegressionHandler
from .text_classification import TextClassificationHandler
from .token_classification import TokenClassificationHandler

__all__ = [
    "TaskHandler",
    "ForecastingHandler",
    "ImageClassificationHandler",
    "ImageSegmentationHandler",
    "ObjectDetectionHandler",
    "TabularClassificationHandler",
    "TabularRegressionHandler",
    "TextClassificationHandler",
    "TokenClassificationHandler",
    "get_task_handler",
    "list_tasks",
    "register_task",
]
