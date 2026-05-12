"""评估业务逻辑：checkout → 落盘数据 → 跑 evaluator → 写 DB。"""
from __future__ import annotations

import json
from pathlib import Path

from .. import db, repo_reader
from ..schema import ModelCardError, ModelCardMetadata, validate_model_card
from .sandbox import model_sandbox


def read_metadata(
    namespace: str, name: str, revision: str,
) -> tuple[str, ModelCardMetadata]:
    """从仓库读 README.md frontmatter 校验后返回 (sha, metadata)。

    Raises:
        FileNotFoundError: README.md 不存在
        ModelCardError: frontmatter 校验失败
    """
    sha = repo_reader.resolve_revision(namespace, name, revision)
    readme = repo_reader.read_file(namespace, name, sha, "README.md")
    if not readme:
        raise FileNotFoundError("README.md 不存在，无法判定 task")
    return sha, validate_model_card(readme)


def run_evaluation(
    eval_id: int,
    namespace: str,
    name: str,
    revision: str,
    dataset_bytes: bytes,
    dataset_name: str,
) -> None:
    """后台 worker：checkout 仓库 + 落盘数据 + 跑 evaluator backend。"""
    from ..runtime.backend import run_evaluation as _run

    db.update_evaluation(eval_id, status="running")

    try:
        with model_sandbox(namespace, name, revision, prefix="mf_eval_") as (workdir, model_dir):
            ds_path = workdir / dataset_name
            ds_path.write_bytes(dataset_bytes)

            readme = (model_dir / "README.md").read_text()
            metadata = validate_model_card(readme)

            result = _run(model_dir, ds_path, metadata)

            db.update_evaluation(
                eval_id,
                status=result.status,
                metrics_json=json.dumps(result.metrics) if result.metrics else None,
                primary_metric=result.primary_metric,
                primary_value=result.primary_value,
                duration_ms=result.duration_ms,
                error=result.error,
            )
    except Exception as e:  # noqa: BLE001
        db.update_evaluation(
            eval_id, status="error", error=f"runner crashed: {e}"
        )
