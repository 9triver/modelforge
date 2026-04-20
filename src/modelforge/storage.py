"""仓库存储管理：在文件系统上创建/查找裸仓库。"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from .config import get_settings

REPO_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class RepoStorageError(Exception):
    pass


def validate_repo_name(name: str) -> None:
    if not REPO_NAME_RE.match(name):
        raise RepoStorageError(
            f"Invalid repo name '{name}'. "
            "允许字母数字、点、下划线、连字符；长度 1-64；首字符必须是字母数字。"
            "（本地化名称请放在 Model Card tags 中）"
        )


def repo_path(name: str) -> Path:
    """裸仓库的物理路径。"""
    return get_settings().repos_dir / f"{name}.git"


def create_bare_repo(name: str) -> Path:
    """创建裸仓库并启用 HTTP 协议（git config http.receivepack）。"""
    validate_repo_name(name)
    path = repo_path(name)
    if path.exists():
        raise RepoStorageError(f"Repository '{name}' already exists")

    settings = get_settings()
    subprocess.run(
        [settings.git_path, "init", "--bare", "--quiet", str(path)],
        check=True,
    )
    # 允许 HTTP push
    subprocess.run(
        [settings.git_path, "config", "http.receivepack", "true"],
        cwd=path, check=True,
    )
    # 允许 anonymous read（push 仍需认证）
    subprocess.run(
        [settings.git_path, "config", "http.uploadpack", "true"],
        cwd=path, check=True,
    )
    install_pre_receive_hook(path)
    return path


def install_pre_receive_hook(repo_path: Path) -> None:
    """在裸仓库里安装 ModelForge pre-receive hook（校验 Model Card）。

    hook 是一个 shell 脚本，调用 Python 执行 modelforge.hooks.pre_receive。
    使用当前服务端 Python 解释器（保证能找到 modelforge 包）。
    """
    hook_path = repo_path / "hooks" / "pre-receive"
    hook_content = f"""#!/bin/sh
# ModelForge pre-receive hook（自动生成）
# 校验 push 的 README.md 是否符合 Model Card 规范
exec {sys.executable} -m modelforge.hooks.pre_receive "$@"
"""
    hook_path.write_text(hook_content)
    hook_path.chmod(0o755)


def delete_bare_repo(name: str) -> None:
    import shutil
    path = repo_path(name)
    if path.exists():
        shutil.rmtree(path)


def repo_exists_on_disk(name: str) -> bool:
    return repo_path(name).is_dir()
