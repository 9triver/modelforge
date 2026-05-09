"""数据集解析辅助：从 dataset_repo 或 UploadFile 获取 (bytes, filename)。"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .. import repo_reader


def resolve_dataset_payload(
    dataset_repo: str,
    revision: str = "main",
    *,
    force_zip: bool = False,
) -> tuple[bytes, str]:
    """从 dataset 仓库解析出数据载荷。

    Args:
        dataset_repo: "namespace/name" 格式
        revision: 分支/SHA
        force_zip: True 时无论是文件还是目录都打 zip

    Returns:
        (payload_bytes, filename)

    Raises:
        ValueError, FileNotFoundError: 仓库或数据不存在
    """
    ds_workdir, ds_path, _ = repo_reader.resolve_dataset_repo(dataset_repo, revision)
    try:
        if not force_zip and ds_path.is_file():
            return ds_path.read_bytes(), ds_path.name

        zip_path = Path(tempfile.mktemp(suffix=".zip"))
        src = str(ds_path) if ds_path.is_dir() else str(ds_path.parent)
        shutil.make_archive(str(zip_path).removesuffix(".zip"), "zip", src)
        try:
            return zip_path.read_bytes(), zip_path.name
        finally:
            zip_path.unlink(missing_ok=True)
    finally:
        shutil.rmtree(ds_workdir, ignore_errors=True)
