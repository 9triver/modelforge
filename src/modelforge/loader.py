"""modelforge.load() — 一行代码加载模型。

    import modelforge
    handler = modelforge.load("amazon/chronos-t5-tiny")
    result = handler.predict(df)
"""
from __future__ import annotations

import os
from pathlib import Path

from .client import ModelHub
from .runtime.evaluator import HandlerLoadError, load_handler
from .runtime.tasks.base import TaskHandler
from .schema import parse_frontmatter

DEFAULT_ENDPOINT = "http://127.0.0.1:8000"


def load(
    repo: str,
    *,
    revision: str = "main",
    endpoint: str | None = None,
    token: str | None = None,
    cache_dir: str | Path | None = None,
) -> TaskHandler:
    """下载模型仓库（有缓存直接用）并返回可调用的 handler 实例。

    Args:
        repo: 仓库名 'namespace/name'
        revision: 分支/tag/commit，默认 main
        endpoint: ModelForge 服务地址，默认 MODELFORGE_URL 环境变量或 127.0.0.1:8000
        token: 认证 token，默认 MODELFORGE_TOKEN 环境变量
        cache_dir: 本地缓存目录，默认 ~/.cache/modelforge

    Returns:
        TaskHandler 子类实例，可直接调 .predict()

    Raises:
        HandlerLoadError: handler.py 缺失或不合法
        ValueError: README.md 缺失或 pipeline_tag 未声明
    """
    ep = endpoint or os.environ.get("MODELFORGE_URL", DEFAULT_ENDPOINT)
    tk = token or os.environ.get("MODELFORGE_TOKEN")
    cd = Path(cache_dir) if cache_dir else None

    hub = ModelHub(ep, token=tk, cache_dir=cd)
    model_dir = hub.snapshot_download(repo, revision=revision)

    readme_path = model_dir / "README.md"
    if not readme_path.is_file():
        raise ValueError(f"{repo}: 缺少 README.md，无法判定 task")

    metadata, _ = parse_frontmatter(readme_path.read_text(encoding="utf-8"))
    task = metadata.get("pipeline_tag")
    if not task:
        raise ValueError(f"{repo}: README.md 的 pipeline_tag 未声明")

    handler = load_handler(model_dir, task)
    handler.warmup()
    return handler
