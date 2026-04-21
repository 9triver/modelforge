"""仓库存储管理：在文件系统上创建/查找裸仓库。

仓库名采用两段格式 `{namespace}/{name}`（如 `amazon/chronos-bolt-tiny`），
磁盘布局：`{repos_dir}/{namespace}/{name}.git/`。
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from .config import get_settings

SEG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class RepoStorageError(Exception):
    pass


def validate_segment(seg: str, label: str) -> None:
    if not SEG_RE.match(seg):
        raise RepoStorageError(
            f"Invalid {label} '{seg}'. "
            "每段允许字母数字、点、下划线、连字符；长度 1-64；首字符必须是字母数字。"
        )


def validate_repo_name(namespace: str, name: str) -> None:
    validate_segment(namespace, "namespace")
    validate_segment(name, "name")


def repo_path(namespace: str, name: str) -> Path:
    """裸仓库的物理路径：{repos_dir}/{namespace}/{name}.git"""
    return get_settings().repos_dir / namespace / f"{name}.git"


def create_bare_repo(namespace: str, name: str) -> Path:
    """创建裸仓库并启用 HTTP 协议（git config http.receivepack）。"""
    validate_repo_name(namespace, name)
    path = repo_path(namespace, name)
    if path.exists():
        raise RepoStorageError(f"Repository '{namespace}/{name}' already exists")

    path.parent.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    subprocess.run(
        [settings.git_path, "init", "--bare", "--quiet", str(path)],
        check=True,
    )
    subprocess.run(
        [settings.git_path, "config", "http.receivepack", "true"],
        cwd=path, check=True,
    )
    subprocess.run(
        [settings.git_path, "config", "http.uploadpack", "true"],
        cwd=path, check=True,
    )
    install_pre_receive_hook(path)
    return path


def install_pre_receive_hook(repo_path: Path) -> None:
    """在裸仓库里安装 ModelForge pre-receive hook（校验 Model Card）。"""
    hook_path = repo_path / "hooks" / "pre-receive"
    hook_content = f"""#!/bin/sh
# ModelForge pre-receive hook（自动生成）
# 校验 push 的 README.md 是否符合 Model Card 规范
exec {sys.executable} -m modelforge.hooks.pre_receive "$@"
"""
    hook_path.write_text(hook_content)
    hook_path.chmod(0o755)


def delete_bare_repo(namespace: str, name: str) -> None:
    import shutil
    path = repo_path(namespace, name)
    if path.exists():
        shutil.rmtree(path)
    # 清理空的 namespace 目录
    ns_dir = path.parent
    try:
        if ns_dir.is_dir() and not any(ns_dir.iterdir()):
            ns_dir.rmdir()
    except OSError:
        pass


def repo_exists_on_disk(namespace: str, name: str) -> bool:
    return repo_path(namespace, name).is_dir()
