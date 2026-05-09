"""模型工作区生命周期管理。

评估、校准、迁移都需要：checkout → (可选 LFS 实化) → 跑任务 → 清理。
本模块提供 context manager 统一管理临时目录生命周期。
"""
from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .. import repo_reader


@contextmanager
def model_workspace(
    namespace: str,
    name: str,
    revision: str,
    *,
    with_lfs: bool = True,
    prefix: str = "mf_workspace_",
):
    """Checkout 模型到临时目录，退出时自动清理。

    Yields:
        (workdir, model_dir) — workdir 是临时根目录，model_dir 是 checkout 出的模型目录
    """
    workdir = Path(tempfile.mkdtemp(prefix=prefix))
    try:
        model_dir = workdir / "model"
        repo_reader.checkout_to_dir(namespace, name, revision, model_dir)
        if with_lfs:
            repo_reader.materialize_lfs(model_dir)
        yield workdir, model_dir
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
