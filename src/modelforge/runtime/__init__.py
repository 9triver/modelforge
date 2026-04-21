"""ModelForge Runtime — 任务化模型执行抽象。

模型仓库里只放 handler.py（继承某个 TaskHandler 子类）+ weights，
评估/推理的数据加载、指标计算、沙箱执行由 runtime 包办。

设计对齐 HuggingFace：pipeline_tag 决定 task，每个 task 有
标准 I/O、标准数据格式、标准指标。详见 ROADMAP.md Phase 2。
"""
from __future__ import annotations

from .tasks.base import TaskHandler

__all__ = ["TaskHandler"]
