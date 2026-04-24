"""Git pre-receive hook：校验每次 push 的 README.md 合规。

调用方式：
  - git-receive-pack 在接受 push 前会执行 $GIT_DIR/hooks/pre-receive
  - stdin 每行格式：<old-sha> <new-sha> <ref>
  - 退出码 0 表示接受，非 0 表示拒绝（并把 stderr 显示给客户端）

逻辑：
  - 对每个非删除的 ref update，读 README.md at new-sha
  - 用 modelforge.schema.validate_model_card 校验
  - 任一失败整个 push 被拒绝
  - 校验通过 → 把 frontmatter 关键字段写入 SQLite repo_cards 表（供搜索）

绕过机制：设置环境变量 MODELFORGE_SKIP_VALIDATION=1（用于紧急情况）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from .. import db
from ..schema import ModelCardError, parse_frontmatter, validate_model_card

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


def _validate_ref(repo_dir: Path, new_sha: str, ref: str) -> tuple[list[str], dict | None]:
    """校验单个 ref update。返回 (错误列表, 解析后的 frontmatter dict)。"""
    readme = _read_file_at_commit(repo_dir, new_sha, "README.md")
    if readme is None:
        return ([
            f"[{ref}] 缺少 README.md。",
            "每个 ModelForge 仓库的根目录必须有 README.md 作为 Model Card。",
        ], None)

    try:
        validate_model_card(readme)
        metadata, _body = parse_frontmatter(readme)
        return ([], metadata)
    except ModelCardError as e:
        return ([f"[{ref}]"] + str(e).split("\n"), None)


def _extract_best_metric(model_index: list | None) -> tuple[str | None, float | None]:
    """从 HF model-index 选出"代表性"指标。优先级：mape > rmse > mae > 第一个。"""
    if not model_index:
        return None, None
    candidates: list[tuple[str, float]] = []
    for entry in model_index:
        for result in entry.get("results", []):
            for m in result.get("metrics") or []:
                name = (m.get("type") or m.get("name") or "").lower()
                val = m.get("value")
                if isinstance(val, (int, float)):
                    candidates.append((name, float(val)))
    if not candidates:
        return None, None
    for preferred in ("mape", "rmse", "mae"):
        for name, val in candidates:
            if preferred in name:
                return preferred, val
    name, val = candidates[0]
    return name, val


def _persist_card(namespace: str, name: str, sha: str, metadata: dict) -> None:
    """把 frontmatter 关键字段写入 SQLite。"""
    repo = db.get_repo(namespace, name)
    if not repo:
        # 仓库未在 DB 注册（比如裸 git init 出来的）→ 跳过
        return

    metric_name, metric_value = _extract_best_metric(metadata.get("model-index"))
    tags = metadata.get("tags") or []
    repo_type = metadata.get("repo_type", "model")
    card = db.RepoCard(
        repo_id=repo.id,
        revision=sha,
        library_name=metadata.get("library_name"),
        pipeline_tag=metadata.get("pipeline_tag"),
        license=metadata.get("license"),
        tags_json=json.dumps(tags, ensure_ascii=False) if tags else None,
        base_model=metadata.get("base_model"),
        best_metric_name=metric_name,
        best_metric_value=metric_value,
        updated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        repo_type=repo_type,
        data_format=metadata.get("data_format"),
    )
    db.upsert_repo_card(card)


def main() -> int:
    if os.environ.get("MODELFORGE_SKIP_VALIDATION") == "1":
        print("modelforge: validation skipped (MODELFORGE_SKIP_VALIDATION=1)", file=sys.stderr)
        return 0

    # repo_dir = {repos_dir}/{namespace}/{name}.git
    repo_dir = Path.cwd()
    name = repo_dir.name.removesuffix(".git")
    namespace = repo_dir.parent.name
    all_errors: list[str] = []
    head_metadata: dict | None = None
    head_sha: str | None = None

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

        errors, metadata = _validate_ref(repo_dir, new_sha, ref)
        all_errors.extend(errors)
        # 只记录 main / master 分支的最新元数据
        if metadata and ref in ("refs/heads/main", "refs/heads/master"):
            head_metadata = metadata
            head_sha = new_sha

    if all_errors:
        print("\n" + "=" * 60, file=sys.stderr)
        print("modelforge: push 被拒绝（Model Card 校验失败）", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        for err in all_errors:
            print(err, file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        return 1

    # 校验通过 → 入库（失败不阻断 push，只打 warning）
    if head_metadata and head_sha:
        try:
            _persist_card(namespace, name, head_sha, head_metadata)
        except Exception as e:
            print(f"modelforge: warning, failed to index card: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
