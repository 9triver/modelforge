"""Workspace 生命周期管理：仓库初始化（子模块）、容器启停、自动保存。"""
from __future__ import annotations

import configparser
import io
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from .. import db, repo_reader, storage
from ..config import get_settings


def _ws_dir(ws_id: int) -> Path:
    return get_settings().workspaces_dir / str(ws_id)


def allocate_port() -> int:
    cfg = get_settings()
    used = set()
    for ws in db.list_workspaces():
        if ws.status in ("creating", "running") and ws.port:
            used.add(ws.port)
    for port in range(cfg.workspace_port_start, cfg.workspace_port_end):
        if port not in used:
            return port
    raise RuntimeError("No available workspace ports")


def _init_space_repo(
    namespace: str,
    name: str,
    models: list[str],
    datasets: list[str],
) -> None:
    """初始化 space 裸仓库：README.md + 子模块挂载模型/数据集。"""
    bare = storage.repo_path(namespace, name)
    cfg = get_settings()
    tmp = cfg.workspaces_dir / "_init_tmp" / f"{namespace}_{name}"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)

    readme_lines = [
        "---",
        "repo_type: space",
        "---",
        "",
        "# " + name,
        "",
        "Workspace for model experimentation.",
        "",
    ]
    (tmp / "README.md").write_text("\n".join(readme_lines), encoding="utf-8")
    (tmp / "notebooks").mkdir(exist_ok=True)
    (tmp / "notebooks" / ".gitkeep").touch()
    (tmp / "scripts").mkdir(exist_ok=True)
    (tmp / "scripts" / ".gitkeep").touch()
    (tmp / "requirements.txt").write_text("", encoding="utf-8")

    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp)], check=True)
    subprocess.run(["git", "-C", str(tmp), "config", "user.email", "modelforge@local"], check=True)
    subprocess.run(["git", "-C", str(tmp), "config", "user.name", "ModelForge"], check=True)

    # 添加模型/数据集为子模块（先用裸仓库绝对路径，commit 前改写为相对路径）
    file_allow = ["-c", "protocol.file.allow=always"]
    for m in models:
        ns, nm = m.split("/", 1)
        model_bare = storage.repo_path(ns, nm)
        subprocess.run(
            ["git", "-C", str(tmp)] + file_allow + ["submodule", "add", str(model_bare), f"models/{nm}"],
            check=True,
        )

    for d in datasets:
        ns, nm = d.split("/", 1)
        ds_bare = storage.repo_path(ns, nm)
        subprocess.run(
            ["git", "-C", str(tmp)] + file_allow + ["submodule", "add", str(ds_bare), f"datasets/{nm}"],
            check=True,
        )

    # 将 .gitmodules 中的绝对 url 改为相对路径 ../../{ns}/{nm}.git
    gitmodules_path = tmp / ".gitmodules"
    if gitmodules_path.exists():
        _rewrite_gitmodules_to_relative(gitmodules_path, models, datasets)
        subprocess.run(
            ["git", "-C", str(tmp), "add", ".gitmodules"],
            check=True,
        )

    subprocess.run(["git", "-C", str(tmp), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp), "commit", "-q", "-m", "init workspace"],
        check=True,
    )
    env = {**os.environ, "MODELFORGE_SKIP_VALIDATION": "1"}
    subprocess.run(
        ["git", "-C", str(tmp), "push", "-q", str(bare), "main"],
        check=True,
        env=env,
    )
    shutil.rmtree(tmp, ignore_errors=True)


def _rewrite_gitmodules_to_relative(
    gitmodules_path: Path,
    models: list[str],
    datasets: list[str],
) -> None:
    """把 .gitmodules 中的绝对裸仓库路径改写为 ../../{ns}/{name}.git 相对路径。"""
    text = gitmodules_path.read_text(encoding="utf-8")

    for m in models:
        ns, nm = m.split("/", 1)
        abs_path = str(storage.repo_path(ns, nm))
        text = text.replace(abs_path, f"../../{ns}/{nm}.git")

    for d in datasets:
        ns, nm = d.split("/", 1)
        abs_path = str(storage.repo_path(ns, nm))
        text = text.replace(abs_path, f"../../{ns}/{nm}.git")

    gitmodules_path.write_text(text, encoding="utf-8")


def _rewrite_submodule_urls_to_local(space_dir: Path) -> None:
    """Clone 后把每个子模块的 url 改写为本地裸仓库绝对路径，以便 submodule update。"""
    gitmodules_path = space_dir / ".gitmodules"
    if not gitmodules_path.exists():
        return

    cp = configparser.ConfigParser()
    cp.read_string(gitmodules_path.read_text(encoding="utf-8"))
    cfg = get_settings()

    for section in cp.sections():
        url = cp.get(section, "url", fallback="")
        path = cp.get(section, "path", fallback="")
        # 相对路径格式: ../../{ns}/{name}.git
        match = re.match(r"\.\./\.\./(.+)/(.+)\.git$", url)
        if match:
            ns, nm = match.group(1), match.group(2)
            local_bare = storage.repo_path(ns, nm)
            subprocess.run(
                ["git", "-C", str(space_dir), "config",
                 f"submodule.{path}.url", str(local_bare)],
                check=False,
            )


def parse_gitmodules(content: str) -> tuple[list[str], list[str]]:
    """解析 .gitmodules 内容，返回 (models, datasets) 的 ns/name 列表。"""
    models: list[str] = []
    datasets: list[str] = []

    cp = configparser.ConfigParser()
    cp.read_string(content)

    for section in cp.sections():
        path = cp.get(section, "path", fallback="")
        url = cp.get(section, "url", fallback="")
        # 从相对 url ../../{ns}/{name}.git 提取 ns/name
        match = re.match(r"\.\./\.\./(.+)/(.+)\.git$", url)
        if match:
            full_name = match.group(1) + "/" + match.group(2)
        else:
            full_name = path.split("/", 1)[-1] if "/" in path else path

        if path.startswith("models/"):
            models.append(full_name)
        elif path.startswith("datasets/"):
            datasets.append(full_name)

    return models, datasets


def create_workspace(
    namespace: str,
    name: str,
    models: list[str],
    datasets: list[str],
    owner_id: int = 1,
) -> int:
    """创建 space 仓库 + DB 记录，返回 workspace_id。"""
    storage.create_bare_repo(namespace, name)
    repo = db.create_repo(namespace, name, owner_id)
    db.upsert_repo_card(db.RepoCard(
        repo_id=repo.id,
        revision="init",
        library_name=None,
        pipeline_tag=None,
        license=None,
        tags_json=None,
        base_model=None,
        best_metric_name=None,
        best_metric_value=None,
        updated_at="",
        repo_type="space",
    ))
    _init_space_repo(namespace, name, models, datasets)

    container_name = "mf-ws-" + uuid.uuid4().hex[:8]
    ws = db.create_workspace(repo.id, container_name)
    return ws.id


def launch_workspace(ws_id: int) -> None:
    """后台 worker：递归 clone 仓库 + 启动 code-server 容器。"""
    cfg = get_settings()
    ws = db.get_workspace(ws_id)
    if not ws:
        return

    try:
        port = allocate_port()
        repo = db.get_repo_by_id(ws.repo_id)
        if not repo:
            raise RuntimeError(f"Workspace repo_id={ws.repo_id} not found")

        namespace, name = repo.namespace, repo.name
        ws_dir = _ws_dir(ws_id)
        ws_dir.mkdir(parents=True, exist_ok=True)

        bare = storage.repo_path(namespace, name)
        space_dir = ws_dir / "space"
        subprocess.run(
            ["git", "clone", str(bare), str(space_dir),
             "--branch", "main", "--single-branch"],
            check=True,
        )

        # 把子模块 url 从相对路径改写为本地裸仓库绝对路径
        _rewrite_submodule_urls_to_local(space_dir)

        # 初始化子模块
        subprocess.run(
            ["git", "-C", str(space_dir), "-c", "protocol.file.allow=always",
             "submodule", "update", "--init"],
            check=True,
        )

        # 对 models/ 下的子模块执行 LFS materialize
        models_dir = space_dir / "models"
        if models_dir.exists():
            for child in models_dir.iterdir():
                if child.is_dir() and (child / ".git").exists():
                    repo_reader.materialize_lfs(child)

        cmd = [
            "docker", "run", "-d",
            "--name", ws.container_name,
            "--memory", cfg.workspace_memory,
            "--cpus", str(cfg.workspace_cpus),
            "-p", f"{port}:8080",
            "-v", f"{space_dir}:/workspace",
            "-w", "/workspace",
            cfg.workspace_image,
            "--bind-addr", "0.0.0.0:8080",
            "--auth", "none",
            "--disable-telemetry",
            "--abs-proxy-base-path", f"/workspaces/{ws_id}",
            "/workspace",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        container_id = result.stdout.strip()[:12]

        db.update_workspace(
            ws_id, status="running",
            container_id=container_id, port=port,
        )
    except Exception as e:  # noqa: BLE001
        db.update_workspace(ws_id, status="error", error=str(e))


def stop_workspace(ws_id: int) -> None:
    """停止 workspace：自动保存子模块 → 保存 space → 停容器 → 清理。"""
    ws = db.get_workspace(ws_id)
    if not ws or ws.status != "running":
        return

    db.update_workspace(ws_id, status="stopping")
    env = {**os.environ, "MODELFORGE_SKIP_VALIDATION": "1"}

    try:
        ws_dir = _ws_dir(ws_id)
        space_dir = ws_dir / "space"

        if space_dir.exists():
            # 先保存每个子模块（models/ 和 datasets/ 下）
            for subdir_name in ("models", "datasets"):
                subdir = space_dir / subdir_name
                if not subdir.exists():
                    continue
                for child in subdir.iterdir():
                    if not child.is_dir() or not (child / ".git").exists():
                        continue
                    subprocess.run(
                        ["git", "-C", str(child), "add", "-A"],
                        check=False,
                    )
                    subprocess.run(
                        ["git", "-C", str(child), "commit", "-q", "-m", "auto-save on stop"],
                        check=False, env=env,
                    )
                    subprocess.run(
                        ["git", "-C", str(child), "push", "-q", "origin", "HEAD"],
                        check=False, env=env,
                    )

            # 保存 space 根目录（会记录更新的 submodule ref）
            subprocess.run(
                ["git", "-C", str(space_dir), "add", "-A"],
                check=False,
            )
            subprocess.run(
                ["git", "-C", str(space_dir), "commit", "-q", "-m", "auto-save on stop"],
                check=False, env=env,
            )
            subprocess.run(
                ["git", "-C", str(space_dir), "push", "-q", "origin", "main"],
                check=False, env=env,
            )

        subprocess.run(["docker", "stop", ws.container_name], check=False)
        subprocess.run(["docker", "rm", ws.container_name], check=False)

        if ws_dir.exists():
            shutil.rmtree(ws_dir, ignore_errors=True)

        db.update_workspace(ws_id, status="stopped")
    except Exception as e:  # noqa: BLE001
        db.update_workspace(ws_id, status="error", error=f"stop failed: {e}")


def restart_workspace(ws_id: int) -> None:
    """重新启动已停止的 workspace。"""
    ws = db.get_workspace(ws_id)
    if not ws or ws.status != "stopped":
        raise ValueError(f"Workspace {ws_id} is not stopped (status={ws.status if ws else 'missing'})")
    launch_workspace(ws_id)
