"""ModelForge Python SDK（对标 huggingface_hub 的三个核心 API）。

核心 API（覆盖日常 95% 场景）：
  - ModelHub.list_repos()        列出所有仓库
  - ModelHub.snapshot_download() 下载整个仓库到本地目录
  - ModelHub.upload_folder()     把本地目录作为一次 commit 推到仓库
  - ModelHub.search()            按 Model Card 字段搜索
  - ModelHub.mirror_from_hf()    从 Hugging Face Hub 镜像模型到 ModelForge

设计原则：
  - 使用者不需要了解 Git / LFS，只想"分享"和"使用"模型
  - 内部复用 `git` 子进程（而非重实现 Git 协议）
  - Token 从参数或环境变量 MODELFORGE_TOKEN 获取
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx

from .schema import ModelCardError, validate_model_card

DEFAULT_CACHE_DIR = Path.home() / ".cache" / "modelforge"

LFS_EXTENSIONS = {
    ".safetensors", ".bin", ".pt", ".pth", ".ckpt", ".h5", ".hdf5",
    ".onnx", ".tflite", ".pb", ".pkl", ".joblib", ".msgpack",
    ".tar", ".gz", ".zip", ".parquet", ".arrow",
}
LFS_SIZE_THRESHOLD = 10 * 1024 * 1024  # 10 MB


@dataclass
class RepoInfo:
    name: str
    owner: str
    is_private: bool
    created_at: str
    git_url: str


@dataclass
class SearchResult:
    name: str
    owner: str
    library_name: str | None
    pipeline_tag: str | None
    license: str | None
    tags: list[str]
    base_model: str | None
    best_metric_name: str | None
    best_metric_value: float | None
    revision: str | None
    updated_at: str | None


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
    def _run_git(args: list[str], cwd: Path | None = None, env: dict | None = None) -> str:
        """运行 git 子进程，失败抛 ModelHubError。返回 stdout。"""
        try:
            result = subprocess.run(
                ["git", *args],
                cwd=cwd,
                env=env or os.environ.copy(),
                check=True,
                capture_output=True,
            )
            return result.stdout.decode("utf-8", errors="replace") if result.stdout else ""
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
            raise ModelHubError(
                f"git {' '.join(args)} 失败（exit {e.returncode}）:\n{stderr}"
            ) from e

    @staticmethod
    def _log(msg: str) -> None:
        print(f"  {msg}", file=sys.stderr, flush=True)

    # ---------- API 1: list_repos ----------

    def list_repos(self) -> list[RepoInfo]:
        """列出平台上所有仓库。"""
        url = f"{self.endpoint}/api/v1/repos"
        try:
            with httpx.Client(trust_env=False, timeout=30.0) as c:
                resp = c.get(url, headers=self._auth_headers())
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ModelHubError(f"list_repos 请求失败：{e}") from e

        return [RepoInfo(**item) for item in resp.json()]

    # ---------- API 1b: search ----------

    def search(
        self,
        library: str | None = None,
        pipeline_tag: str | None = None,
        license: str | None = None,
        tag: str | None = None,
        metric: str | None = None,
        max_metric: float | None = None,
        limit: int = 100,
    ) -> list[SearchResult]:
        """按 Model Card 字段搜索仓库。

        Examples:
            hub.search(library="lightgbm", metric="mape", max_metric=4.0)
            hub.search(tag="time-series-forecasting")
        """
        params: dict = {}
        if library:
            params["library"] = library
        if pipeline_tag:
            params["pipeline_tag"] = pipeline_tag
        if license:
            params["license"] = license
        if tag:
            params["tag"] = tag
        if metric:
            params["metric"] = metric
        if max_metric is not None:
            params["max_metric"] = max_metric
        params["limit"] = limit

        url = f"{self.endpoint}/api/v1/repos/search"
        try:
            with httpx.Client(trust_env=False, timeout=30.0) as c:
                resp = c.get(url, params=params, headers=self._auth_headers())
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise ModelHubError(f"search 请求失败：{e}") from e

        return [
            SearchResult(
                name=item["name"],
                owner=item["owner"],
                library_name=item.get("library_name"),
                pipeline_tag=item.get("pipeline_tag"),
                license=item.get("license"),
                tags=item.get("tags", []),
                base_model=item.get("base_model"),
                best_metric_name=item.get("best_metric_name"),
                best_metric_value=item.get("best_metric_value"),
                revision=item.get("revision"),
                updated_at=item.get("updated_at"),
            )
            for item in resp.json()
        ]

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

    @staticmethod
    def _detect_lfs_patterns(folder: Path) -> set[str]:
        """扫描目录，返回需要 LFS 追踪的 glob 模式集合。

        规则：文件后缀在 LFS_EXTENSIONS 中，或文件大小超过 LFS_SIZE_THRESHOLD。
        """
        patterns: set[str] = set()
        for f in folder.rglob("*"):
            if not f.is_file() or f.name.startswith("."):
                continue
            suffix = f.suffix.lower()
            if suffix in LFS_EXTENSIONS or f.stat().st_size > LFS_SIZE_THRESHOLD:
                patterns.add(f"*{suffix}")
        return patterns

    @staticmethod
    def _setup_lfs_tracking(workdir: Path, source_folder: Path) -> None:
        """配置 LFS 追踪：优先复用源目录的 .gitattributes，否则自动检测。"""
        src_attrs = source_folder / ".gitattributes"
        if src_attrs.is_file():
            shutil.copy2(src_attrs, workdir / ".gitattributes")
            return

        patterns = ModelHub._detect_lfs_patterns(source_folder)
        if not patterns:
            return

        for pat in sorted(patterns):
            subprocess.run(
                ["git", "lfs", "track", pat],
                cwd=workdir, capture_output=True,
            )

    def upload_folder(
        self,
        repo_name: str,
        folder_path: str | Path,
        commit_message: str,
        branch: str = "main",
        tag: str | None = None,
        verbose: bool = True,
    ) -> str:
        """把本地目录的全部内容作为一次 commit 推到仓库。

        自动检测大文件并配置 LFS 追踪。如果源目录已有 .gitattributes 则直接复用。

        Args:
            repo_name: 目标仓库名
            folder_path: 本地源目录
            commit_message: commit 信息
            branch: 目标分支，默认 main
            tag: 可选的 tag（如 "v1.1"），push 后会额外打并推
            verbose: 是否输出进度信息

        Returns:
            新 commit 的 SHA
        """
        log = self._log if verbose else lambda _: None
        folder_path = Path(folder_path).resolve()
        if not folder_path.is_dir():
            raise ModelHubError(f"folder_path 不是目录：{folder_path}")

        # 统计文件
        all_files = [f for f in folder_path.rglob("*") if f.is_file() and f.name != ".git"]
        total_size = sum(f.stat().st_size for f in all_files)
        log(f"📦 {len(all_files)} files, {total_size / 1e6:.1f} MB total")

        # 1. 本地预校验
        readme = folder_path / "README.md"
        if not readme.is_file():
            raise ModelHubError(f"{folder_path} 缺少 README.md")
        try:
            validate_model_card(readme.read_text(encoding="utf-8"))
        except ModelCardError as e:
            raise ModelHubError(f"本地 Model Card 校验失败：\n{e}") from e
        log("✓ Model Card 校验通过")

        git_url = self._authenticated_git_url(repo_name)

        with tempfile.TemporaryDirectory(prefix="modelforge-upload-") as tmp:
            workdir = Path(tmp) / repo_name
            log(f"⬇ Cloning {repo_name}...")
            self._run_git(["clone", "--quiet", git_url, str(workdir)])

            # LFS 初始化
            try:
                self._run_git(["lfs", "install", "--local"], cwd=workdir)
            except ModelHubError:
                pass

            # 切换/创建分支
            result = subprocess.run(
                ["git", "rev-parse", "--verify", f"origin/{branch}"],
                cwd=workdir, capture_output=True,
            )
            if result.returncode == 0:
                self._run_git(["checkout", "-B", branch, f"origin/{branch}"], cwd=workdir)
            else:
                self._run_git(["checkout", "-B", branch], cwd=workdir)

            # 清空工作区（保留 .git）
            for child in workdir.iterdir():
                if child.name == ".git":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()

            # 配置 LFS 追踪（在复制文件之前）
            self._setup_lfs_tracking(workdir, folder_path)
            lfs_attrs = workdir / ".gitattributes"
            if lfs_attrs.is_file():
                tracked = [l.split()[0] for l in lfs_attrs.read_text().splitlines() if "filter=lfs" in l]
                if tracked:
                    log(f"🔗 LFS tracking: {', '.join(tracked)}")

            # 复制源目录内容
            log("📋 Copying files...")
            for child in folder_path.iterdir():
                if child.name == ".git":
                    continue
                dest = workdir / child.name
                if child.name == ".gitattributes" and lfs_attrs.is_file():
                    continue  # 已经处理过
                if child.is_dir():
                    shutil.copytree(child, dest)
                else:
                    shutil.copy2(child, dest)

            # 提交
            self._run_git(["add", "-A"], cwd=workdir)

            diff = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=workdir,
            )
            if diff.returncode == 0:
                sha = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=workdir, text=True,
                ).strip()
                log("⚡ No changes, skipping push")
                return sha

            env = os.environ.copy()
            env.setdefault("GIT_AUTHOR_NAME", self.username)
            env.setdefault("GIT_AUTHOR_EMAIL", f"{self.username}@modelforge")
            env.setdefault("GIT_COMMITTER_NAME", self.username)
            env.setdefault("GIT_COMMITTER_EMAIL", f"{self.username}@modelforge")

            self._run_git(["commit", "-m", commit_message], cwd=workdir, env=env)

            log(f"⬆ Pushing to {repo_name} ({branch})...")
            self._run_git(["push", "origin", branch], cwd=workdir)

            if tag:
                self._run_git(["tag", tag], cwd=workdir)
                self._run_git(["push", "origin", tag], cwd=workdir)
                log(f"🏷 Tagged {tag}")

            sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=workdir, text=True,
            ).strip()
            log(f"✓ Done: {sha[:8]}")
            return sha

    # ---------- API 5: mirror_from_hf ----------

    def mirror_from_hf(
        self,
        hf_repo_id: str,
        repo_name: str | None = None,
        revision: str = "main",
        commit_message: str | None = None,
        tag: str | None = None,
    ) -> str:
        """从 Hugging Face Hub 下载模型并推送到 ModelForge。

        需要安装 huggingface_hub：pip install huggingface_hub

        Args:
            hf_repo_id: HF 仓库 ID，如 "google/timesfm-2.0-500m-pytorch"
            repo_name: ModelForge 仓库名（默认取 HF repo 的 model name 部分）
            revision: HF 上的 revision
            commit_message: commit 信息（默认自动生成）
            tag: 可选 tag

        Returns:
            新 commit 的 SHA
        """
        try:
            from huggingface_hub import snapshot_download as hf_download
        except ImportError:
            raise ModelHubError(
                "mirror_from_hf 需要 huggingface_hub：pip install huggingface_hub"
            )

        if repo_name is None:
            repo_name = hf_repo_id.split("/")[-1]

        self._log(f"⬇ Downloading {hf_repo_id} from Hugging Face...")
        local_dir = Path(tempfile.mkdtemp(prefix="modelforge-hf-")) / repo_name
        hf_download(
            hf_repo_id,
            revision=revision,
            local_dir=str(local_dir),
        )

        self._log(f"⬆ Pushing to ModelForge as '{repo_name}'...")
        msg = commit_message or f"Mirror from HF: {hf_repo_id} ({revision})"
        try:
            return self.upload_folder(repo_name, local_dir, msg, tag=tag)
        finally:
            shutil.rmtree(local_dir.parent, ignore_errors=True)
