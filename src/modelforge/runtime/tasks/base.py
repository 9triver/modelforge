"""TaskHandler 基类 + 任务注册表。

模型作者在仓库里写：

    # handler.py
    from modelforge.runtime.tasks import ForecastingHandler

    class Handler(ForecastingHandler):
        def __init__(self, model_dir: str):
            self.model = load_from(model_dir)

        def predict(self, df):
            return self.model.forecast(df)

平台（评估 runner）按 model_card.yaml 的 pipeline_tag 找到对应
TaskHandler 子类，与仓库里的 Handler 做 isinstance 校验后加载。
"""
from __future__ import annotations

from typing import Any, ClassVar


class TaskHandler:
    """所有任务 handler 的抽象基类。

    子类必须覆盖 `task`（= pipeline_tag）。
    `__init__(model_dir)` 里做 weights 加载等一次性工作；
    `predict(inputs)` 签名由 task 子类进一步约束。
    """

    task: ClassVar[str] = ""

    def __init__(self, model_dir: str) -> None:
        self.model_dir = model_dir

    def predict(self, inputs: Any) -> Any:  # noqa: D401 — 抽象方法
        raise NotImplementedError

    def warmup(self) -> None:
        """可选：预热钩子（JIT 编译、CUDA init 等）。默认 no-op。"""


_REGISTRY: dict[str, type[TaskHandler]] = {}


def register_task(cls: type[TaskHandler]) -> type[TaskHandler]:
    """TaskHandler 子类注册到全局表，按 cls.task 索引。"""
    if not cls.task:
        raise ValueError(f"{cls.__name__} 缺少 task classvar")
    if cls.task in _REGISTRY and _REGISTRY[cls.task] is not cls:
        raise ValueError(f"task '{cls.task}' 已被 {_REGISTRY[cls.task].__name__} 注册")
    _REGISTRY[cls.task] = cls
    return cls


def get_task_handler(task: str) -> type[TaskHandler]:
    """按 pipeline_tag 取对应的 TaskHandler 基类。"""
    if task not in _REGISTRY:
        raise KeyError(
            f"未知 task '{task}'。已注册：{sorted(_REGISTRY)}"
        )
    return _REGISTRY[task]


def list_tasks() -> list[str]:
    return sorted(_REGISTRY)
