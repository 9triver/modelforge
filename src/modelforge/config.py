"""应用配置：所有路径和服务参数。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """支持环境变量 MODELFORGE_* 覆盖。"""

    model_config = SettingsConfigDict(
        env_prefix="MODELFORGE_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # 数据根目录
    data_dir: Path = Path.home() / "modelforge-data"

    # 服务监听
    host: str = "127.0.0.1"
    port: int = 8000

    # Git 协议
    git_http_backend_path: str = ""   # 留空则自动探测 `git --exec-path`/git-http-backend
    git_path: str = "git"

    # 单文件 LFS 上传上限（字节）
    lfs_max_object_size: int = 10 * 1024 * 1024 * 1024  # 10 GB

    # Evaluator backend: "inprocess"（默认，无隔离）或 "docker"（容器沙箱）
    eval_backend: str = "inprocess"
    docker_image_prefix: str = "modelforge-runtime"
    docker_memory: str = "8g"
    docker_cpus: int = 4
    docker_timeout: int = 300
    docker_gpu: bool = False

    # ===== 派生路径（基于 data_dir）=====
    @property
    def repos_dir(self) -> Path:
        return self.data_dir / "repos"

    @property
    def lfs_dir(self) -> Path:
        return self.data_dir / "lfs-objects"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "modelforge.db"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.repos_dir, self.lfs_dir):
            p.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def get_settings() -> Settings:
    """全局单例。"""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_dirs()
    return _settings


def reset_settings(**overrides) -> Settings:
    """测试用：重置并替换设置。"""
    global _settings
    _settings = Settings(**overrides)
    _settings.ensure_dirs()
    return _settings
