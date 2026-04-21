"""从裸仓库直接读取内容（不 clone），用于 Web UI 和预览场景。

通过 `git --git-dir=... show <ref>:<file>` 或 `ls-tree` 操作裸仓库。
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import storage


@dataclass
class FileEntry:
    """裸仓库里一个文件的元信息。"""
    path: str          # 相对路径
    size: int          # 字节大小
    is_lfs: bool       # 是否为 LFS 指针
    mode: str          # Git 模式（100644/100755/120000/...）


def _git(namespace: str, name: str, *args: str) -> str:
    """在裸仓库上运行 git 命令，返回 stdout（字符串）。"""
    path = storage.repo_path(namespace, name)
    result = subprocess.run(
        ["git", f"--git-dir={path}", *args],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise FileNotFoundError(
            f"git {' '.join(args)} 失败: {result.stderr.strip()}"
        )
    return result.stdout


def read_file(namespace: str, name: str, revision: str, filepath: str) -> str | None:
    """读取仓库中某 revision 下的文本文件。不存在返回 None。"""
    try:
        return _git(namespace, name, "show", f"{revision}:{filepath}")
    except FileNotFoundError:
        return None


def list_files(namespace: str, name: str, revision: str) -> list[FileEntry]:
    """列出仓库某 revision 下所有文件（递归）。

    识别 LFS 指针（尺寸 <1KB 且以 'version https://git-lfs.github.com' 开头的 blob）。
    返回 [FileEntry, ...]。
    """
    try:
        output = _git(namespace, name, "ls-tree", "-r", "-l", revision)
    except FileNotFoundError:
        return []

    entries: list[FileEntry] = []
    for line in output.splitlines():
        # 格式: <mode> <type> <hash> <size|->\t<path>
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        mode, obj_type, obj_hash, size_str, path = parts
        if obj_type != "blob":
            continue
        size = int(size_str) if size_str != "-" else 0

        is_lfs = False
        # 小文件可能是 LFS 指针；检查内容
        if 0 < size < 1024:
            try:
                content = _git(namespace, name, "show", f"{revision}:{path}")
                if content.startswith("version https://git-lfs.github.com"):
                    is_lfs = True
                    for ln in content.split("\n"):
                        if ln.startswith("size "):
                            try:
                                size = int(ln[5:])
                            except ValueError:
                                pass
            except FileNotFoundError:
                pass

        entries.append(FileEntry(path=path, size=size, is_lfs=is_lfs, mode=mode))
    return entries


def has_any_commits(namespace: str, name: str) -> bool:
    """仓库是否有任何 commit（判断是不是空仓库）。"""
    try:
        _git(namespace, name, "rev-parse", "HEAD")
        return True
    except FileNotFoundError:
        return False


def resolve_revision(namespace: str, name: str, revision: str) -> str:
    """把 'main' / tag / short sha 解析成完整 commit sha。"""
    return _git(namespace, name, "rev-parse", revision).strip()


def checkout_to_dir(namespace: str, name: str, revision: str, dest: Path) -> None:
    """把裸仓库的某 revision 内容释放到 dest 目录。

    不做真正的 clone（省磁盘），用 `git archive | tar` pipe。
    LFS 指针文件**不会**被替换成真实大文件——caller 如需要 LFS 内容，
    要另行通过 lfs_store 取。
    """
    dest.mkdir(parents=True, exist_ok=True)
    bare = storage.repo_path(namespace, name)
    # git archive 输出 tar，交给 tar -x 解压
    archive = subprocess.Popen(
        ["git", f"--git-dir={bare}", "archive", revision],
        stdout=subprocess.PIPE,
    )
    tar = subprocess.Popen(
        ["tar", "-x", "-C", str(dest)],
        stdin=archive.stdout,
    )
    archive.stdout.close()  # SIGPIPE 给 archive 进程
    tar_rc = tar.wait()
    archive_rc = archive.wait()
    if archive_rc != 0 or tar_rc != 0:
        raise RuntimeError(
            f"checkout failed: git archive rc={archive_rc}, tar rc={tar_rc}"
        )


def list_refs(namespace: str, name: str) -> dict[str, list[str]]:
    """列出仓库的分支和 tag。返回 {"branches": [...], "tags": [...]}。"""
    branches: list[str] = []
    tags: list[str] = []
    try:
        output = _git(namespace, name, "for-each-ref", "--format=%(refname)", "refs/heads/", "refs/tags/")
    except FileNotFoundError:
        return {"branches": branches, "tags": tags}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("refs/heads/"):
            branches.append(line.removeprefix("refs/heads/"))
        elif line.startswith("refs/tags/"):
            tags.append(line.removeprefix("refs/tags/"))
    return {"branches": branches, "tags": tags}
