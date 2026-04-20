"""ModelForge Python SDK（对标 huggingface_hub 的三个核心 API）。

核心 API（覆盖日常 95% 场景）：
  - ModelHub.list_repos()        列出所有仓库
  - ModelHub.snapshot_download() 下载整个仓库到本地目录
  - ModelHub.upload_folder()     把本地目录作为一次 commit 推到仓库

设计原则：
  - 使用者不需要了解 Git / LFS，只想"分享"和"使用"模型
  - 内部复用 `git` 子进程（而非重实现 Git 协议）
  - Token 从参数或环境变量 MODELFORGE_TOKEN 获取
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx

from .schema import ModelCardError, validate_model_card

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "modelforge"


@dataclass
class RepoInfo:
    name: str
    owner: str
    is_private: bool
    created_at: str
    git_url: str


class ModelHubError(Exception):
    """所有 SDK 错误的基类。"""


class ModelHub:
    """ModelForge 客户端。

    Examples:
        hub = ModelHub("http://localhost:8000", token="mf_xxx")
        repos = hub.list_repos()
        local_dir = hub.snapshot_download("苏州")
        hub.upload_folder("苏州", "./my-trained-model/", "v1.1 tuned")
    """

    def __init__(
        self,
        endpoint: str,
        token: str | None = None,
        cache_dir: Path | None = None,
        username: str = "modelforge",
    ):
        self.endpoint = endpoint.rstrip("/")
        self.token = token or os.environ.get("MODELFORGE_TOKEN")
        self.cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.username = username  # HTTP Basic Auth 的 username，内容无关紧要

    # ---------- 内部工具 ----------

    def _auth_headers(self) -> dict:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    def _authenticated_git_url(self, repo_name: str) -> str:
        """构造带认证信息的 Git URL（用于传给 git 子进程）。"""
        if not self.token:
            return f"{self.endpoint}/{repo_name}.git"
        parsed = urlparse(self.endpoint)
        netloc = f"{self.username}:{self.token}@{parsed.netloc}"
        return urlunparse((parsed.scheme, netloc, parsed.path, "", "", "")) + f"/{repo_name}.git"

    @staticmethod
    def _run_git(args: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
        """运行 git 子进程，失败抛 ModelHubError。"""
        try:
            subprocess.run(
                ["git", *args],
                cwd=cwd,
                env=env or os.environ.copy(),
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
            raise ModelHubError(
                f"git {' '.join(args)} 失败（exit {e.returncode}）:\n{stderr}"
            ) from e

    # ---------- API 1: list_repos ----------

    def list_repos(self) -> list[RepoInfo]:
        """列出平台上所有仓库。"""
        url = f"{self.endpoint}/api/v1/repos"
        try:
            # trust_env=False 避免系统 HTTP_PROXY / ALL_PROXY 干扰本地调用
            with httpx.Client(trust_env=False, timeout=30.0) as c:
                resp = c.get(url, headers=self._auth_headers())
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ModelHubError(f"list_repos 请求失败：{e}") from e

        return [RepoInfo(**item) for item in resp.json()]

    # ---------- API 2: snapshot_download ----------

    def snapshot_download(
        self,
        repo_name: str,
        revision: str = "main",
        local_dir: Path | None = None,
    ) -> Path:
        """下载整个仓库到本地目录（含 LFS 物件）。

        缓存位置：`{cache_dir}/snapshots/{repo_name}/{revision_resolved}/`
        如果已缓存相同 revision 的内容，直接返回缓存路径；不强制重新下载。

        Args:
            repo_name: 仓库名，如 "苏州"
            revision: 分支名/tag/commit SHA，默认 "main"
            local_dir: 强制下载到指定目录（不使用缓存）

        Returns:
            指向本地目录的 Path
        """
        target_dir = local_dir or (self.cache_dir / "snapshots" / repo_name / revision)

        # 已存在且有内容 → 直接用缓存
        if target_dir.is_dir() and any(target_dir.iterdir()):
            return target_dir

        target_dir.parent.mkdir(parents=True, exist_ok=True)
        git_url = self._authenticated_git_url(repo_name)

        # Clone
        self._run_git(["clone", "--quiet", git_url, str(target_dir)])

        # Checkout 指定 revision（默认 main 已经在头上，除非指定其他）
        if revision != "main":
            self._run_git(["checkout", "--quiet", revision], cwd=target_dir)

        # LFS pull（如果有大文件）
        try:
            self._run_git(["lfs", "pull"], cwd=target_dir)
        except ModelHubError:
            # 仓库可能没配置 LFS，不是错误
            pass

        return target_dir

    # ---------- API 3: upload_folder ----------

    def upload_folder(
        self,
        repo_name: str,
        folder_path: str | Path,
        commit_message: str,
        branch: str = "main",
        tag: str | None = None,
    ) -> str:
        """把本地目录的全部内容作为一次 commit 推到仓库。

        工作流程：
          1. 本地校验 README.md 符合 Model Card 规范（提前失败，不浪费往返）
          2. 克隆仓库到临时目录
          3. 把目录内容复制覆盖进去（保留 .git）
          4. commit + push；可选打 tag

        Args:
            repo_name: 目标仓库名
            folder_path: 本地源目录
            commit_message: commit 信息
            branch: 目标分支，默认 main
            tag: 可选的 tag（如 "v1.1"），push 后会额外打并推

        Returns:
            新 commit 的 SHA
        """
        folder_path = Path(folder_path).resolve()
        if not folder_path.is_dir():
            raise ModelHubError(f"folder_path 不是目录：{folder_path}")

        # 1. 本地预校验
        readme = folder_path / "README.md"
        if not readme.is_file():
            raise ModelHubError(f"{folder_path} 缺少 README.md")
        try:
            validate_model_card(readme.read_text(encoding="utf-8"))
        except ModelCardError as e:
            raise ModelHubError(f"本地 Model Card 校验失败：\n{e}") from e

        git_url = self._authenticated_git_url(repo_name)

        with tempfile.TemporaryDirectory(prefix="modelforge-upload-") as tmp:
            workdir = Path(tmp) / repo_name
            # Clone（支持已有内容的仓库，也支持空仓库）
            self._run_git(["clone", "--quiet", git_url, str(workdir)])

            # 确保有 LFS 客户端初始化
            try:
                self._run_git(["lfs", "install", "--local"], cwd=workdir)
            except ModelHubError:
                pass

            # 2. 切换/创建分支
            result = subprocess.run(
                ["git", "rev-parse", "--verify", f"origin/{branch}"],
                cwd=workdir, capture_output=True,
            )
            if result.returncode == 0:
                self._run_git(["checkout", "-B", branch, f"origin/{branch}"], cwd=workdir)
            else:
                # 空仓库或分支不存在
                self._run_git(["checkout", "-B", branch], cwd=workdir)

            # 3. 清空工作区（保留 .git）后复制源目录内容
            for child in workdir.iterdir():
                if child.name == ".git":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()

            for child in folder_path.iterdir():
                if child.name == ".git":
                    continue
                dest = workdir / child.name
                if child.is_dir():
                    shutil.copytree(child, dest)
                else:
                    shutil.copy2(child, dest)

            # 4. 提交
            self._run_git(["add", "-A"], cwd=workdir)

            # 检查是否有改动
            diff = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=workdir,
            )
            if diff.returncode == 0:
                # 无改动
                sha = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=workdir, text=True,
                ).strip()
                return sha

            # 配置提交作者（借用 Token 身份）
            env = os.environ.copy()
            env.setdefault("GIT_AUTHOR_NAME", self.username)
            env.setdefault("GIT_AUTHOR_EMAIL", f"{self.username}@modelforge")
            env.setdefault("GIT_COMMITTER_NAME", self.username)
            env.setdefault("GIT_COMMITTER_EMAIL", f"{self.username}@modelforge")

            self._run_git(["commit", "-m", commit_message], cwd=workdir, env=env)

            # Push
            self._run_git(["push", "origin", branch], cwd=workdir)

            # Tag（可选）
            if tag:
                self._run_git(["tag", tag], cwd=workdir)
                self._run_git(["push", "origin", tag], cwd=workdir)

            sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=workdir, text=True,
            ).strip()
            return sha
