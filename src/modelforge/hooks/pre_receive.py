"""Git pre-receive hook：校验每次 push 的 README.md 合规。

调用方式：
  - git-receive-pack 在接受 push 前会执行 $GIT_DIR/hooks/pre-receive
  - stdin 每行格式：<old-sha> <new-sha> <ref>
  - 退出码 0 表示接受，非 0 表示拒绝（并把 stderr 显示给客户端）

逻辑：
  - 对每个非删除的 ref update，读 README.md at new-sha
  - 用 modelforge.schema.validate_model_card 校验
  - 任一失败整个 push 被拒绝

绕过机制：设置环境变量 MODELFORGE_SKIP_VALIDATION=1（用于紧急情况）
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ..schema import ModelCardError, validate_model_card

ZERO_SHA = "0" * 40
ZERO_SHA_256 = "0" * 64  # Git SHA-256 支持


def _is_deletion(new_sha: str) -> bool:
    return new_sha in (ZERO_SHA, ZERO_SHA_256)


def _read_file_at_commit(repo_dir: Path, sha: str, filepath: str) -> str | None:
    """从裸仓库读取指定 commit 下的文件内容。文件不存在返回 None。"""
    try:
        content = subprocess.check_output(
            ["git", f"--git-dir={repo_dir}", "show", f"{sha}:{filepath}"],
            stderr=subprocess.DEVNULL,
        )
        return content.decode("utf-8", errors="replace")
    except subprocess.CalledProcessError:
        return None


def _validate_ref(repo_dir: Path, new_sha: str, ref: str) -> list[str]:
    """校验单个 ref update。返回错误信息列表（空表示通过）。"""
    readme = _read_file_at_commit(repo_dir, new_sha, "README.md")
    if readme is None:
        return [
            f"[{ref}] 缺少 README.md。",
            "每个 ModelForge 仓库的根目录必须有 README.md 作为 Model Card。",
        ]

    try:
        validate_model_card(readme)
    except ModelCardError as e:
        return [f"[{ref}]"] + str(e).split("\n")

    return []


def main() -> int:
    if os.environ.get("MODELFORGE_SKIP_VALIDATION") == "1":
        print("modelforge: validation skipped (MODELFORGE_SKIP_VALIDATION=1)", file=sys.stderr)
        return 0

    repo_dir = Path.cwd()
    all_errors: list[str] = []

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 3:
            continue
        old_sha, new_sha, ref = parts

        if _is_deletion(new_sha):
            continue

        errors = _validate_ref(repo_dir, new_sha, ref)
        all_errors.extend(errors)

    if all_errors:
        print("\n" + "=" * 60, file=sys.stderr)
        print("modelforge: push 被拒绝（Model Card 校验失败）", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        for err in all_errors:
            print(err, file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
